; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; amiga_gfx.i - OS custom-screen graphics runtime for HAS
; Contract: docs/AMIGA_OS_GFX_API.md
; =============================================================================

    ifnd AMIGA_GFX_I
AMIGA_GFX_I = 1

GFX_LIB_VERSION     EQU 37

GFX_MODE_LORES      EQU 0
GFX_MODE_HIRES      EQU $8000
GFX_MODE_LACE       EQU $0004
GFX_MODE_SPRITES    EQU $4000

GFX_EVT_NONE        EQU 0
GFX_EVT_CLOSE       EQU 1

GFX_MAX_BITMAPS     EQU 8
GFX_MAX_SPRITES     EQU 8

; ViewPort Modes (graphics/view.i)
HIRES               EQU $8000
LACE                EQU $0004
SPRITES             EQU $4000

; Screen type
CUSTOMSCREEN        EQU $000F
SCREENQUIET         EQU $0100

; NewScreen offsets (32 bytes)
NS_LEFTEDGE         EQU 0
NS_TOPEDGE          EQU 2
NS_WIDTH            EQU 4
NS_HEIGHT           EQU 6
NS_DEPTH            EQU 8
NS_DETAILPEN        EQU 10
NS_BLOCKPEN         EQU 11
NS_VIEWMODES        EQU 12
NS_TYPE             EQU 14
NS_FONT             EQU 16
NS_DEFAULTTITLE     EQU 20
NS_GADGETS          EQU 24
NS_CUSTOMBITMAP     EQU 28
NS_SIZEOF           EQU 32

; Screen embedded ViewPort / RastPort
SC_VIEWPORT         EQU 44
SC_RASTPORT         EQU 84

; RastPort.TmpRas (graphics/rastport.i) — required by Flood()
RP_TMPRAS           EQU 12
TR_SIZEOF           EQU 8

; NewWindow (shared with gui_intuition.i values)
NW_LEFTEDGE         EQU 0
NW_TOPEDGE          EQU 2
NW_WIDTH            EQU 4
NW_HEIGHT           EQU 6
NW_DETAILPEN        EQU 8
NW_BLOCKPEN         EQU 9
NW_IDCMPFLAGS       EQU 10
NW_FLAGS            EQU 14
NW_FIRSTGADGET      EQU 18
NW_CHECKMARK        EQU 22
NW_TITLE            EQU 26
NW_SCREEN           EQU 30
NW_BITMAP           EQU 34
NW_MINWIDTH         EQU 38
NW_MINHEIGHT        EQU 40
NW_MAXWIDTH         EQU 42
NW_MAXHEIGHT        EQU 44
NW_TYPE             EQU 46
NW_SIZEOF           EQU 48

WD_RPORT            EQU 50
WD_USERPORT         EQU 86
MP_SIGBIT           EQU 15
IM_CLASS            EQU 20
IM_CODE             EQU 24

IDCMP_CLOSEWINDOW   EQU $00000200
IDCMP_VANILLAKEY    EQU $00200000

WFLG_BACKDROP       EQU $00000100
WFLG_BORDERLESS     EQU $00000800
WFLG_ACTIVATE       EQU $00001000
WFLG_RMBTRAP        EQU $00010000
WFLG_NOCAREREFRESH  EQU $00020000

JAM1                EQU 0

MEMF_PUBLIC         EQU (1<<0)
MEMF_CHIP           EQU (1<<1)
MEMF_CLEAR          EQU (1<<16)

; BitMap
BM_BYTESPERROW      EQU 0
BM_ROWS             EQU 2
BM_FLAGS            EQU 4
BM_DEPTH            EQU 5
BM_PAD              EQU 6
BM_PLANES           EQU 8
BM_SIZEOF           EQU 40

; SimpleSprite
SS_POSCTLDATA       EQU 0
SS_HEIGHT           EQU 4
SS_X                EQU 6
SS_Y                EQU 8
SS_NUM              EQU 10
SS_SIZEOF           EQU 12

; intuition.library LVOs (not in gui_intuition for OpenScreen)
_LVOCloseScreen     EQU -66
_LVOCloseWindow     EQU -72
_LVOModifyIDCMP     EQU -150
_LVOOpenScreen      EQU -198
_LVOOpenWindow      EQU -204

    endif ; AMIGA_GFX_I
