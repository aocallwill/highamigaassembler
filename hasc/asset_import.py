"""Compile-time PNG asset import for #import bob|palette|sprite directives.

Orchestrates tools/bob_importer.py, tools/amiga_palette.py, and
tools/sprite_importer.py; does not reimplement quantization. Generates .s
fragments under an asset outdir with mtime + options-fingerprint caching.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default when CLI does not pass --asset-outdir
DEFAULT_ASSET_OUTDIR = "build/gen"

# Hardware sprites are always one 16-pixel-wide DMA channel (2 planes / 4 colours).
SPRITE_WIDTH_PX = 16
SPRITE_PLANES = 2
SPRITE_COLORS = 4

_IMPORT_RE = re.compile(
    r'^#import\s+(bob|palette|sprite)\s+"([^"]+)"\s+as\s+([A-Za-z_][A-Za-z0-9_]*)'
    r'(?P<opts>(?:\s+[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_]+)?)*)\s*;?\s*$'
)

# Values: identifiers, decimals, 0x/hex, or $hex (for vstart/vstop).
_OPT_RE = re.compile(
    r'([A-Za-z_][A-Za-z0-9_]*)(?:=(0[xX][0-9A-Fa-f]+|\$[0-9A-Fa-f]+|[A-Za-z0-9_]+))?'
)


@dataclass
class AssetImport:
    """One resolved #import (bob, palette, or sprite)."""
    kind: str  # 'bob' | 'palette' | 'sprite'
    source_path: str  # absolute PNG path
    label: str
    options: Dict[str, Any] = field(default_factory=dict)
    gen_path: str = ""  # absolute path to generated .s


def _parse_bool_opt(value: Any, line_no: int, name: str) -> bool:
    if value is True or str(value).lower() in ("1", "true", "yes", "on"):
        return True
    if value is False or str(value).lower() in ("0", "false", "no", "off"):
        return False
    raise SyntaxError(
        f"Preprocessor error at line {line_no}: invalid {name} value"
    )


def _parse_int_opt(value: Any, line_no: int, name: str) -> int:
    """Accept decimal or 0x/$ hex integers for import options."""
    if isinstance(value, int):
        return int(value)
    s = str(value).strip()
    try:
        if s.startswith(("0x", "0X")):
            return int(s, 16)
        if s.startswith("$"):
            return int(s[1:], 16)
        return int(s, 10)
    except (TypeError, ValueError):
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: {name} must be an integer"
        ) from None


def _tools_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "tools"


def _load_tool(module_name: str, filename: str):
    """Load a tools/*.py module by path (tools/ is not always a package)."""
    path = _tools_dir() / filename
    if not path.exists():
        raise RuntimeError(f"Asset tool not found: {path}")
    # Prefer already-imported module (tests / package layout).
    pkg_name = f"tools.{module_name}"
    if pkg_name in sys.modules:
        return sys.modules[pkg_name]
    if module_name in sys.modules and getattr(sys.modules[module_name], "__file__", "").endswith(filename):
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(f"hasc_asset_{module_name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load asset tool: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def parse_import_line(stripped: str, line_no: int) -> Tuple[str, str, str, Dict[str, Any]]:
    """
    Parse `#import kind "path" as label [opts...];`.

    Returns (kind, path_raw, label, options).
    """
    m = _IMPORT_RE.match(stripped)
    if not m:
        # Narrower diagnostics for common mistakes
        if stripped.startswith("#import"):
            if ' as ' not in stripped:
                raise SyntaxError(
                    f"Preprocessor error at line {line_no}: "
                    f"#import requires 'as <label>' (e.g. #import bob \"x.png\" as my_bob;)"
                )
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: invalid #import syntax: {stripped}"
            )
        raise SyntaxError(f"Preprocessor error at line {line_no}: not an #import line")

    kind = m.group(1)
    path_raw = m.group(2)
    label = m.group(3)
    opts_blob = (m.group("opts") or "").strip()
    options: Dict[str, Any] = {}
    if opts_blob:
        for om in _OPT_RE.finditer(opts_blob):
            key = om.group(1)
            val = om.group(2)
            if key in options:
                raise SyntaxError(
                    f"Preprocessor error at line {line_no}: duplicate option '{key}' in #import"
                )
            if val is None:
                options[key] = True  # flag form (add_word, requantize)
            else:
                options[key] = val
    return kind, path_raw, label, options


def _normalize_bob_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {"planes", "dither", "add_word"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown bob import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "planes": 5,
        "dither": "none",
        "add_word": False,
    }
    if "planes" in options:
        try:
            planes = int(options["planes"])
        except (TypeError, ValueError):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: bob planes must be 1..5"
            ) from None
        if planes < 1 or planes > 5:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: bob planes must be 1..5"
            )
        out["planes"] = planes
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"bob dither must be none|fs (got {d!r})"
            )
        out["dither"] = d
    if "add_word" in options:
        # Extra empty 16px word so the blitter can shift the BOB to any X
        # (cookie-cut / A shift); planar width becomes ceil16(w)+16.
        out["add_word"] = _parse_bool_opt(options["add_word"], line_no, "add_word")
    return out


def _normalize_sprite_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {"dither", "vstart", "vstop", "planes", "colors"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown sprite import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "dither": "none",
        "vstart": 0x10,
        "vstop": 0x20,
        "planes": SPRITE_PLANES,
        "colors": SPRITE_COLORS,
    }
    if "planes" in options:
        planes = _parse_int_opt(options["planes"], line_no, "planes")
        if planes != SPRITE_PLANES:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"hardware sprites are fixed at {SPRITE_PLANES} bitplanes "
                f"({SPRITE_COLORS} colours); got planes={planes}"
            )
    if "colors" in options:
        colors = _parse_int_opt(options["colors"], line_no, "colors")
        if colors != SPRITE_COLORS:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"hardware sprites are fixed at {SPRITE_COLORS} colours "
                f"(2 bitplanes); got colors={colors}"
            )
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"sprite dither must be none|fs (got {d!r})"
            )
        out["dither"] = d
    if "vstart" in options:
        out["vstart"] = _parse_int_opt(options["vstart"], line_no, "vstart") & 0x1FF
    if "vstop" in options:
        out["vstop"] = _parse_int_opt(options["vstop"], line_no, "vstop") & 0x1FF
    return out


def _normalize_palette_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {"colors", "planes", "dither", "index0", "requantize"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown palette import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    if "colors" in options and "planes" in options:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"palette import: use only one of colors= or planes="
        )
    out: Dict[str, Any] = {
        "colors": 32,
        "dither": "none",
        "index0": "backdrop",
        "requantize": False,
    }
    if "planes" in options:
        try:
            planes = int(options["planes"])
        except (TypeError, ValueError):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette planes must be 1..5"
            ) from None
        if planes < 1 or planes > 5:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette planes must be 1..5"
            )
        out["colors"] = 2 ** planes
    elif "colors" in options:
        try:
            colors = int(options["colors"])
        except (TypeError, ValueError):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette colors must be 2..32"
            ) from None
        if colors < 2 or colors > 32:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette colors must be 2..32"
            )
        out["colors"] = colors
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs", "ordered"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"palette dither must be none|fs|ordered (got {d!r})"
            )
        out["dither"] = d
    if "index0" in options:
        i0 = str(options["index0"]).lower()
        if i0 not in ("backdrop", "transparent", "none"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"index0 must be backdrop|transparent|none"
            )
        out["index0"] = i0
    if "requantize" in options:
        out["requantize"] = _parse_bool_opt(options["requantize"], line_no, "requantize")
    return out


def _fingerprint(kind: str, label: str, options: Dict[str, Any], source_path: str) -> str:
    payload = {
        "kind": kind,
        "label": label,
        "options": options,
        "source": os.path.basename(source_path),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _meta_path(gen_path: Path) -> Path:
    return gen_path.with_suffix(gen_path.suffix + ".import.json")


def _tool_mtimes(kind: str) -> List[float]:
    tools = _tools_dir()
    paths = [Path(__file__)]
    if kind == "bob":
        paths.append(tools / "bob_importer.py")
    elif kind == "sprite":
        paths.append(tools / "sprite_importer.py")
    else:
        paths.append(tools / "amiga_palette.py")
    mtimes = []
    for p in paths:
        try:
            mtimes.append(p.stat().st_mtime)
        except OSError:
            mtimes.append(0.0)
    return mtimes


def _png_size(source_path: Path) -> Tuple[int, int]:
    from PIL import Image

    with Image.open(str(source_path)) as img:
        return img.size


def _require_sprite_width(source_path: Path, line_no: int) -> None:
    """Hardware sprites are one DMA channel: exactly 16 pixels wide."""
    w, h = _png_size(source_path)
    if w != SPRITE_WIDTH_PX:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"hardware sprite PNG must be exactly {SPRITE_WIDTH_PX} pixels wide "
            f"(got {w}x{h} from {source_path.name}); "
            f"resize or crop the source — #import will not stretch it"
        )


def _cache_is_fresh(
    gen_path: Path,
    source_path: Path,
    kind: str,
    fingerprint: str,
) -> bool:
    if not gen_path.is_file():
        return False
    meta = _meta_path(gen_path)
    if not meta.is_file():
        return False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("fingerprint") != fingerprint:
        return False
    try:
        gen_mtime = gen_path.stat().st_mtime
        src_mtime = source_path.stat().st_mtime
    except OSError:
        return False
    if gen_mtime < src_mtime:
        return False
    for tm in _tool_mtimes(kind):
        if gen_mtime < tm:
            return False
    return True


def _write_cache_meta(gen_path: Path, fingerprint: str, kind: str, label: str) -> None:
    meta = {
        "fingerprint": fingerprint,
        "kind": kind,
        "label": label,
    }
    _meta_path(gen_path).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _ensure_pillow() -> None:
    try:
        from PIL import Image  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "Pillow is required for #import (pip install pillow)"
        ) from exc


def _generate_bob(source_path: Path, label: str, options: Dict[str, Any], gen_path: Path) -> None:
    bob = _load_tool("bob_importer", "bob_importer.py")
    use_dither = options["dither"] == "fs"
    asm = bob.export_bob_asm(
        str(source_path),
        label,
        planes=int(options["planes"]),
        use_dither=use_dither,
        add_word=bool(options["add_word"]),
    )
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import bob as {label}\n{asm}\n",
        encoding="utf-8",
    )


def _generate_palette(source_path: Path, label: str, options: Dict[str, Any], gen_path: Path) -> None:
    ap = _load_tool("amiga_palette", "amiga_palette.py")
    result = ap.convert_image(
        source_path,
        colors=int(options["colors"]),
        dither=str(options["dither"]),
        index0=str(options["index0"]),
        requantize=bool(options["requantize"]),
    )
    ap.write_palette_asm(
        gen_path,
        label,
        result["palette_words"],
        source_name=source_path.name,
        num_colors=int(options["colors"]),
        section="data,DATA",
    )


def _generate_sprite(source_path: Path, label: str, options: Dict[str, Any], gen_path: Path) -> None:
    sprite = _load_tool("sprite_importer", "sprite_importer.py")
    use_dither = options["dither"] == "fs"
    asm = sprite.export_sprite_asm(
        str(source_path),
        label,
        vstart=int(options["vstart"]),
        vstop=int(options["vstop"]),
        use_dither=use_dither,
    )
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import sprite as {label}\n{asm}\n",
        encoding="utf-8",
    )


def process_import(
    kind: str,
    path_raw: str,
    label: str,
    options: Dict[str, Any],
    *,
    current_dir: str,
    asset_outdir: str,
    force: bool = False,
    line_no: int = 0,
) -> AssetImport:
    """Resolve, convert (or reuse cache), and return an AssetImport record."""
    if kind == "bob":
        norm = _normalize_bob_options(options, line_no)
    elif kind == "palette":
        norm = _normalize_palette_options(options, line_no)
    elif kind == "sprite":
        norm = _normalize_sprite_options(options, line_no)
    else:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"unknown #import kind '{kind}' (expected bob|palette|sprite)"
        )

    if os.path.isabs(path_raw):
        source_path = Path(os.path.normpath(path_raw))
    else:
        source_path = Path(os.path.normpath(os.path.join(current_dir, path_raw)))

    if not source_path.is_file():
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: #import file not found: {source_path}"
        )

    outdir = Path(asset_outdir)
    if not outdir.is_absolute():
        outdir = Path(os.getcwd()) / outdir
    gen_path = outdir / f"{label}.s"
    fingerprint = _fingerprint(kind, label, norm, str(source_path))

    if force or not _cache_is_fresh(gen_path, source_path, kind, fingerprint):
        _ensure_pillow()
        if kind == "sprite":
            # Enforce before export: do not silently resize non-16px sources.
            _require_sprite_width(source_path, line_no)
            _generate_sprite(source_path, label, norm, gen_path)
        elif kind == "bob":
            _generate_bob(source_path, label, norm, gen_path)
        else:
            _generate_palette(source_path, label, norm, gen_path)
        _write_cache_meta(gen_path, fingerprint, kind, label)

    return AssetImport(
        kind=kind,
        source_path=str(source_path.resolve()),
        label=label,
        options=norm,
        gen_path=str(gen_path.resolve()),
    )


def include_path_for_output(gen_path: str, output_path: Optional[str] = None) -> str:
    """Path string suitable for vasm INCLUDE relative to the output .s when possible."""
    gen = Path(gen_path).resolve()
    if output_path:
        try:
            rel = os.path.relpath(str(gen), start=str(Path(output_path).resolve().parent))
            return rel.replace(os.sep, "/")
        except ValueError:
            pass
    try:
        rel = os.path.relpath(str(gen), start=os.getcwd())
        return rel.replace(os.sep, "/")
    except ValueError:
        return str(gen).replace(os.sep, "/")
