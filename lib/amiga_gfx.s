; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; amiga_gfx.s - OS custom-screen graphics for HAS (68000-safe)
; Contract: docs/AMIGA_OS_GFX_API.md
; =============================================================================

    include "hardware.i"
    include "exec_lib.i"
    include "graphics_lib.i"
    include "amiga_gfx.i"

    SECTION amiga_gfx_data,DATA
    CNOP 0,4

gfx_int_name:   dc.b "intuition.library",0
    even
gfx_gfx_name:   dc.b "graphics.library",0
    even
gfx_title:      dc.b "HAS Gfx",0
    even

gfx_int_base:   dc.l 0
gfx_gfx_base:   dc.l 0
gfx_screen:     dc.l 0
gfx_window:     dc.l 0
gfx_rp:         dc.l 0
gfx_vp:         dc.l 0

gfx_bm_ptr:     ds.l GFX_MAX_BITMAPS
gfx_bm_w:       ds.w GFX_MAX_BITMAPS
gfx_bm_h:       ds.w GFX_MAX_BITMAPS
gfx_bm_depth:   ds.w GFX_MAX_BITMAPS

gfx_ss:         ds.b GFX_MAX_SPRITES*SS_SIZEOF
gfx_ss_owned:   ds.l GFX_MAX_SPRITES
gfx_ss_used:    ds.w GFX_MAX_SPRITES

gfx_ns:         ds.b NS_SIZEOF
gfx_nw:         ds.b NW_SIZEOF
gfx_tmp_rp:     ds.b 100

; Flood()/AreaFill scratch — chip plane + TmpRas header (InitTmpRas)
gfx_tmpras:     ds.b TR_SIZEOF
gfx_tmpras_buf: dc.l 0
gfx_tmpras_w:   dc.w 0
gfx_tmpras_h:   dc.w 0

    SECTION amiga_gfx_code,CODE

    XDEF GfxInit
    XDEF GfxShutdown
    XDEF GfxOpenScreen
    XDEF GfxCloseScreen
    XDEF GfxWaitTOF
    XDEF GfxInk
    XDEF GfxColor
    XDEF GfxPlot
    XDEF GfxLine
    XDEF GfxRect
    XDEF GfxCircle
    XDEF GfxFill
    XDEF GfxText
    XDEF GfxAllocBitMap
    XDEF GfxFreeBitMap
    XDEF GfxBitMapClear
    XDEF GfxBitMapPlot
    XDEF GfxBlit
    XDEF GfxSpriteGet
    XDEF GfxSpriteData
    XDEF GfxSpriteMove
    XDEF GfxSpriteFree
    XDEF GfxWaitEvent

; =============================================================================
GfxInit:
    link a6,#0
    ; a6 must be saved: library calls use a6 as base; unlk needs the frame
    movem.l d1-d7/a0-a6,-(sp)
    move.l gfx_int_base,d0
    beq .gi_open
    move.l gfx_gfx_base,d0
    beq .gi_open
    moveq #0,d0
    bra .gi_done
.gi_open:
    move.l ExecBase,a6
    tst.l gfx_int_base
    bne .gi_have_int
    lea gfx_int_name,a1
    moveq #GFX_LIB_VERSION,d0
    jsr _LVOOpenLibrary(a6)
    move.l d0,gfx_int_base
    beq .gi_fail
.gi_have_int:
    lea gfx_gfx_name,a1
    moveq #GFX_LIB_VERSION,d0
    jsr _LVOOpenLibrary(a6)
    move.l d0,gfx_gfx_base
    bne .gi_ok
    move.l gfx_int_base,a1
    jsr _LVOCloseLibrary(a6)
    clr.l gfx_int_base
    bra .gi_fail
.gi_ok:
    moveq #0,d0
    bra .gi_done
.gi_fail:
    moveq #-1,d0
.gi_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

GfxShutdown:
    link a6,#0
    movem.l d0-d7/a0-a6,-(sp)
    bsr gfx_do_close_screen
    move.l ExecBase,a6
    move.l gfx_gfx_base,d0
    beq .gs_nografic
    move.l d0,a1
    jsr _LVOCloseLibrary(a6)
    clr.l gfx_gfx_base
.gs_nografic:
    move.l gfx_int_base,d0
    beq .gs_noint
    move.l d0,a1
    jsr _LVOCloseLibrary(a6)
    clr.l gfx_int_base
.gs_noint:
    movem.l (sp)+,d0-d7/a0-a6
    unlk a6
    rts

; =============================================================================
GfxOpenScreen:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5                          ; frame (params); a6 becomes lib base
    tst.l gfx_int_base
    beq .gos_fail
    tst.l gfx_gfx_base
    beq .gos_fail
    tst.l gfx_screen
    bne .gos_fail

    lea gfx_ns,a0
    moveq #(NS_SIZEOF/2)-1,d0
.gos_clrns:
    clr.w (a0)+
    dbra d0,.gos_clrns
    lea gfx_ns,a0
    move.l 8(a5),d0
    move.w d0,NS_LEFTEDGE(a0)
    move.l 12(a5),d0
    move.w d0,NS_TOPEDGE(a0)
    move.l 16(a5),d0
    move.w d0,NS_WIDTH(a0)
    move.l 20(a5),d0
    move.w d0,NS_HEIGHT(a0)
    move.l 24(a5),d0
    cmp.l #1,d0
    bge .gos_d1
    moveq #1,d0
.gos_d1:
    cmp.l #5,d0
    ble .gos_d2
    moveq #5,d0
.gos_d2:
    move.w d0,NS_DEPTH(a0)
    clr.b NS_DETAILPEN(a0)
    move.b #1,NS_BLOCKPEN(a0)
    move.l 28(a5),d0
    and.l #HIRES!LACE!SPRITES,d0
    move.w d0,NS_VIEWMODES(a0)
    move.w #CUSTOMSCREEN!SCREENQUIET,NS_TYPE(a0)
    lea gfx_title,a1
    move.l a1,NS_DEFAULTTITLE(a0)

    move.l gfx_int_base,a6
    jsr _LVOOpenScreen(a6)
    move.l d0,gfx_screen
    beq .gos_fail
    move.l d0,a0
    lea SC_VIEWPORT(a0),a1
    move.l a1,gfx_vp
    ; Prefer Window->RPort once open (layered); provisional screen RP until then
    lea SC_RASTPORT(a0),a1
    move.l a1,gfx_rp

    lea gfx_nw,a0
    moveq #(NW_SIZEOF/2)-1,d0
.gos_clrnw:
    clr.w (a0)+
    dbra d0,.gos_clrnw
    lea gfx_nw,a0
    move.l 16(a5),d0
    move.w d0,NW_WIDTH(a0)
    move.l 20(a5),d0
    move.w d0,NW_HEIGHT(a0)
    clr.b NW_DETAILPEN(a0)
    move.b #1,NW_BLOCKPEN(a0)
    move.l #IDCMP_CLOSEWINDOW!IDCMP_VANILLAKEY,NW_IDCMPFLAGS(a0)
    move.l #WFLG_BORDERLESS!WFLG_ACTIVATE!WFLG_RMBTRAP!WFLG_BACKDROP!WFLG_NOCAREREFRESH,NW_FLAGS(a0)
    move.l gfx_screen,NW_SCREEN(a0)
    move.w #$FFFF,NW_MAXWIDTH(a0)
    move.w #$FFFF,NW_MAXHEIGHT(a0)
    move.w #CUSTOMSCREEN,NW_TYPE(a0)

    move.l gfx_int_base,a6
    jsr _LVOOpenWindow(a6)
    move.l d0,gfx_window
    beq .gos_win_fail
    move.l d0,a0
    move.l WD_RPORT(a0),d1
    beq .gos_win_fail
    move.l d1,gfx_rp

    ; Flood() requires chip TmpRas on the RastPort we draw into
    move.l 16(a5),d0                    ; width
    move.l 20(a5),d1                    ; height
    bsr gfx_setup_tmpras
    tst.l d0
    beq .gos_tmpras_fail

    move.l gfx_gfx_base,a6
    move.l gfx_rp,a1
    moveq #JAM1,d0
    jsr _LVOSetDrMd(a6)
    move.l gfx_rp,a1
    moveq #1,d0
    jsr _LVOSetAPen(a6)

    move.l gfx_screen,d0
    bra .gos_done
.gos_tmpras_fail:
.gos_win_fail:
    bsr gfx_close_window_safely
.gos_close_scr:
    move.l gfx_screen,d0
    beq .gos_fail
    move.l d0,a0
    move.l gfx_int_base,a6
    jsr _LVOCloseScreen(a6)
    clr.l gfx_screen
    clr.l gfx_rp
    clr.l gfx_vp
    bra .gos_fail
.gos_fail:
    moveq #0,d0
.gos_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; d0=width, d1=height -> d0=1 ok / 0 fail. Attaches TmpRas to gfx_rp.
gfx_setup_tmpras:
    movem.l d1-d3/a0-a1/a6,-(sp)
    move.l d0,d2
    move.l d1,d3
    ble .stm_fail
    tst.l d2
    ble .stm_fail
    tst.l gfx_rp
    beq .stm_fail
    tst.l gfx_gfx_base
    beq .stm_fail
    bsr gfx_free_tmpras
    move.l gfx_gfx_base,a6
    move.l d2,d0
    move.l d3,d1
    jsr _LVOAllocRaster(a6)
    tst.l d0
    beq .stm_fail
    move.l d0,gfx_tmpras_buf
    move.w d2,gfx_tmpras_w
    move.w d3,gfx_tmpras_h
    ; size = RASSIZE(w,h) = (((w+15)>>4)*2)*h
    move.l d2,d0
    add.l #15,d0
    lsr.l #4,d0
    add.l d0,d0
    move.l d3,d1
    mulu d1,d0                          ; demo sizes fit 16-bit product
    lea gfx_tmpras,a0
    move.l gfx_tmpras_buf,a1
    move.l gfx_gfx_base,a6
    jsr _LVOInitTmpRas(a6)
    move.l gfx_rp,a0
    lea gfx_tmpras,a1
    move.l a1,RP_TMPRAS(a0)
    moveq #1,d0
    bra .stm_done
.stm_fail:
    moveq #0,d0
.stm_done:
    movem.l (sp)+,d1-d3/a0-a1/a6
    rts

gfx_free_tmpras:
    movem.l d0-d1/a0-a1/a6,-(sp)
    move.l gfx_rp,d0
    beq .ftm_buf
    move.l d0,a0
    clr.l RP_TMPRAS(a0)
.ftm_buf:
    move.l gfx_tmpras_buf,d0
    beq .ftm_done
    move.l gfx_gfx_base,d1
    beq .ftm_clr
    move.l d1,a6
    move.l d0,a0
    moveq #0,d0
    move.w gfx_tmpras_w,d0
    moveq #0,d1
    move.w gfx_tmpras_h,d1
    jsr _LVOFreeRaster(a6)
.ftm_clr:
    clr.l gfx_tmpras_buf
    clr.w gfx_tmpras_w
    clr.w gfx_tmpras_h
.ftm_done:
    movem.l (sp)+,d0-d1/a0-a1/a6
    rts

GfxCloseScreen:
    link a6,#0
    movem.l d0-d7/a0-a6,-(sp)
    bsr gfx_do_close_screen
    movem.l (sp)+,d0-d7/a0-a6
    unlk a6
    rts

gfx_do_close_screen:
    movem.l d0-d7/a0-a6,-(sp)
    bsr gfx_free_all_sprites
    bsr gfx_free_all_bitmaps
    ; Detach TmpRas while Window->RPort is still valid
    bsr gfx_free_tmpras
    bsr gfx_close_window_safely
    move.l gfx_screen,d0
    beq .dcs_done
    move.l d0,a0
    move.l gfx_int_base,d1
    beq .dcs_clr
    move.l d1,a6
    jsr _LVOCloseScreen(a6)
.dcs_clr:
    clr.l gfx_screen
    clr.l gfx_rp
    clr.l gfx_vp
.dcs_done:
    movem.l (sp)+,d0-d7/a0-a6
    rts

gfx_close_window_safely:
    movem.l d0-d2/a0-a2/a6,-(sp)
    move.l gfx_window,d0
    beq .cws_done
    move.l d0,a2
    move.l WD_USERPORT(a2),d1
    beq .cws_close
.cws_drain:
    move.l WD_USERPORT(a2),a0
    move.l ExecBase,a6
    jsr _LVOGetMsg(a6)
    tst.l d0
    beq .cws_drained
    move.l d0,a1
    jsr _LVOReplyMsg(a6)
    bra .cws_drain
.cws_drained:
    clr.l WD_USERPORT(a2)
    move.l gfx_int_base,a6
    move.l a2,a0
    moveq #0,d0
    jsr _LVOModifyIDCMP(a6)
.cws_close:
    move.l gfx_int_base,a6
    move.l a2,a0
    jsr _LVOCloseWindow(a6)
    clr.l gfx_window
.cws_done:
    movem.l (sp)+,d0-d2/a0-a2/a6
    rts

GfxWaitTOF:
    link a6,#0
    movem.l d0/a6,-(sp)
    move.l gfx_gfx_base,d0
    beq .wtof_done
    move.l d0,a6
    jsr _LVOWaitTOF(a6)
.wtof_done:
    movem.l (sp)+,d0/a6
    unlk a6
    rts

GfxInk:
    link a6,#0
    movem.l d0/a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_rp
    beq .ink_done
    move.l gfx_gfx_base,a6
    move.l gfx_rp,a1
    move.l 8(a5),d0
    jsr _LVOSetAPen(a6)
.ink_done:
    movem.l (sp)+,d0/a1/a5-a6
    unlk a6
    rts

gfx_clamp15:
    tst.l d1
    bpl .cl0
    moveq #0,d1
.cl0:
    cmp.l #15,d1
    ble .cl1
    moveq #15,d1
.cl1:
    rts

GfxColor:
    link a6,#0
    movem.l d0-d3/a0/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_vp
    beq .col_done
    move.l 12(a5),d1
    bsr gfx_clamp15
    move.l d1,-(sp)
    move.l 16(a5),d1
    bsr gfx_clamp15
    move.l d1,-(sp)
    move.l 20(a5),d1
    bsr gfx_clamp15
    move.l d1,d3
    move.l (sp)+,d2
    move.l (sp)+,d1
    move.l gfx_gfx_base,a6
    move.l gfx_vp,a0
    move.l 8(a5),d0
    jsr _LVOSetRGB4(a6)
.col_done:
    movem.l (sp)+,d0-d3/a0/a5-a6
    unlk a6
    rts

GfxPlot:
    link a6,#0
    movem.l d0-d1/a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_rp
    beq .plot_done
    move.l gfx_gfx_base,a6
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    jsr _LVOWritePixel(a6)
.plot_done:
    movem.l (sp)+,d0-d1/a1/a5-a6
    unlk a6
    rts

GfxLine:
    link a6,#0
    movem.l d0-d1/a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_rp
    beq .line_done
    move.l gfx_gfx_base,a6
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    jsr _LVOMove(a6)
    move.l gfx_rp,a1
    move.l 16(a5),d0
    move.l 20(a5),d1
    jsr _LVODraw(a6)
.line_done:
    movem.l (sp)+,d0-d1/a1/a5-a6
    unlk a6
    rts

GfxRect:
    link a6,#0
    movem.l d0-d4/a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_rp
    beq .rect_done
    move.l 16(a5),d2
    ble .rect_done
    move.l 20(a5),d3
    ble .rect_done
    move.l gfx_gfx_base,a6
    tst.l 24(a5)
    beq .rect_box
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    move.l d0,d4
    add.l d2,d4
    subq.l #1,d4
    move.l d1,d2
    add.l d3,d2
    subq.l #1,d2
    move.l d2,d3
    move.l d4,d2
    jsr _LVORectFill(a6)
    bra .rect_done
.rect_box:
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    jsr _LVOMove(a6)
    move.l gfx_rp,a1
    move.l 8(a5),d0
    add.l 16(a5),d0
    subq.l #1,d0
    move.l 12(a5),d1
    jsr _LVODraw(a6)
    move.l gfx_rp,a1
    move.l 8(a5),d0
    add.l 16(a5),d0
    subq.l #1,d0
    move.l 12(a5),d1
    add.l 20(a5),d1
    subq.l #1,d1
    jsr _LVODraw(a6)
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    add.l 20(a5),d1
    subq.l #1,d1
    jsr _LVODraw(a6)
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    jsr _LVODraw(a6)
.rect_done:
    movem.l (sp)+,d0-d4/a1/a5-a6
    unlk a6
    rts

GfxCircle:
    link a6,#0
    movem.l d0-d7/a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_rp
    beq .cir_done
    move.l 16(a5),d7
    ble .cir_done
    move.l gfx_gfx_base,a6
    tst.l 20(a5)
    bne .cir_fill
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    move.l d7,d2
    move.l d7,d3
    jsr _LVODrawEllipse(a6)
    bra .cir_done
.cir_fill:
    move.l d7,d6
    neg.l d6
.cir_y:
    moveq #0,d5
.cir_x:
    move.l d5,d0
    muls d5,d0
    move.l d6,d1
    muls d6,d1
    add.l d1,d0
    move.l d7,d1
    muls d7,d1
    cmp.l d1,d0
    bgt .cir_xd
    addq.l #1,d5
    bra .cir_x
.cir_xd:
    subq.l #1,d5
    bmi .cir_yn
    move.l gfx_rp,a1
    move.l 8(a5),d0
    sub.l d5,d0
    move.l 12(a5),d1
    add.l d6,d1
    move.l 8(a5),d2
    add.l d5,d2
    move.l d1,d3
    jsr _LVORectFill(a6)
.cir_yn:
    addq.l #1,d6
    cmp.l d7,d6
    ble .cir_y
.cir_done:
    movem.l (sp)+,d0-d7/a1/a5-a6
    unlk a6
    rts

GfxFill:
    link a6,#0
    movem.l d0-d2/a0-a1/a5-a6,-(sp)
    move.l a6,a5
    move.l gfx_rp,d0
    beq .fill_done
    move.l d0,a0
    ; Flood crashes if RastPort.TmpRas is NULL (amiga_gfx_demo GfxFill path)
    tst.l RP_TMPRAS(a0)
    beq .fill_done
    tst.l gfx_tmpras_buf
    beq .fill_done
    move.l gfx_gfx_base,a6
    move.l gfx_rp,a1
    moveq #1,d2                         ; mode 1: fill matching seed pen
    move.l 8(a5),d0
    move.l 12(a5),d1
    jsr _LVOFlood(a6)
.fill_done:
    movem.l (sp)+,d0-d2/a0-a1/a5-a6
    unlk a6
    rts

GfxText:
    link a6,#0
    movem.l d0-d1/a0-a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_rp
    beq .txt_done
    move.l 16(a5),a0
    move.l a0,d0
    beq .txt_done
    move.l gfx_gfx_base,a6
    move.l gfx_rp,a1
    move.l 8(a5),d0
    move.l 12(a5),d1
    jsr _LVOMove(a6)
    move.l 16(a5),a0
    moveq #-1,d0
.txt_len:
    addq.l #1,d0
    tst.b (a0)+
    bne .txt_len
    move.l gfx_rp,a1
    move.l 16(a5),a0
    jsr _LVOText(a6)
.txt_done:
    movem.l (sp)+,d0-d1/a0-a1/a5-a6
    unlk a6
    rts

; =============================================================================
gfx_free_all_bitmaps:
    move.l d2,-(sp)
    moveq #0,d2
.fab_loop:
    cmp.w #GFX_MAX_BITMAPS,d2
    bge .fab_done
    move.l d2,d0
    bsr gfx_free_bm_slot
    addq.w #1,d2
    bra .fab_loop
.fab_done:
    move.l (sp)+,d2
    rts

; Input: d0 = slot
gfx_free_bm_slot:
    movem.l d0-d6/a0-a3/a6,-(sp)
    move.l d0,d6                    ; slot
    lea gfx_bm_ptr,a0
    move.l d6,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l (a0),d0
    beq .fbs_done
    move.l d0,a2                    ; BitMap*
    lea gfx_bm_w,a0
    move.l d6,d1
    add.l d1,d1
    adda.l d1,a0
    move.w (a0),d2                  ; w
    lea gfx_bm_h,a0
    move.l d6,d1
    add.l d1,d1
    adda.l d1,a0
    move.w (a0),d3                  ; h
    lea gfx_bm_depth,a0
    move.l d6,d1
    add.l d1,d1
    adda.l d1,a0
    move.w (a0),d4                  ; depth
    moveq #0,d5                     ; plane
    lea BM_PLANES(a2),a3
.fbs_plane:
    cmp.w d4,d5
    bge .fbs_freestruct
    move.l (a3)+,d0
    beq .fbs_nextp
    move.l gfx_gfx_base,a6
    move.l d0,a0
    move.w d2,d0
    ext.l d0
    move.w d3,d1
    ext.l d1
    jsr _LVOFreeRaster(a6)
.fbs_nextp:
    addq.w #1,d5
    bra .fbs_plane
.fbs_freestruct:
    move.l ExecBase,a6
    move.l a2,a1
    move.l #BM_SIZEOF,d0
    jsr _LVOFreeMem(a6)
    lea gfx_bm_ptr,a0
    move.l d6,d1
    lsl.l #2,d1
    adda.l d1,a0
    clr.l (a0)
    lea gfx_bm_w,a0
    move.l d6,d1
    add.l d1,d1
    adda.l d1,a0
    clr.w (a0)
    lea gfx_bm_h,a0
    move.l d6,d1
    add.l d1,d1
    adda.l d1,a0
    clr.w (a0)
    lea gfx_bm_depth,a0
    move.l d6,d1
    add.l d1,d1
    adda.l d1,a0
    clr.w (a0)
.fbs_done:
    movem.l (sp)+,d0-d6/a0-a3/a6
    rts

; find free bitmap slot -> d0=slot or -1
gfx_find_bm_slot:
    moveq #0,d0
.fbm:
    cmp.w #GFX_MAX_BITMAPS,d0
    bge .fbm_fail
    lea gfx_bm_ptr,a0
    move.l d0,d1
    lsl.l #2,d1
    adda.l d1,a0
    tst.l (a0)
    beq .fbm_ok
    addq.w #1,d0
    bra .fbm
.fbm_fail:
    moveq #-1,d0
.fbm_ok:
    rts

; handle in d0 -> slot in d0 or -1
gfx_handle_to_slot:
    move.l d0,d2
    moveq #0,d0
.hts:
    cmp.w #GFX_MAX_BITMAPS,d0
    bge .hts_fail
    lea gfx_bm_ptr,a0
    move.l d0,d1
    lsl.l #2,d1
    adda.l d1,a0
    cmp.l (a0),d2
    beq .hts_ok
    addq.w #1,d0
    bra .hts
.hts_fail:
    moveq #-1,d0
.hts_ok:
    rts

GfxAllocBitMap:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5
    tst.l gfx_gfx_base
    beq .gab_fail
    move.l 8(a5),d2                 ; w
    move.l 12(a5),d3                ; h
    move.l 16(a5),d4                ; depth
    ble .gab_fail
    tst.l d2
    ble .gab_fail
    tst.l d3
    ble .gab_fail
    cmp.l #1,d4
    bge .gab_d1
    moveq #1,d4
.gab_d1:
    cmp.l #8,d4
    ble .gab_d2
    moveq #8,d4
.gab_d2:
    bsr gfx_find_bm_slot
    move.l d0,d7                    ; slot
    bmi .gab_fail

    move.l ExecBase,a6
    move.l #BM_SIZEOF,d0
    move.l #MEMF_PUBLIC!MEMF_CLEAR,d1
    jsr _LVOAllocMem(a6)
    tst.l d0
    beq .gab_fail
    move.l d0,a4                    ; BitMap*
    move.l gfx_gfx_base,a6
    move.l a4,a0
    move.l d4,d0                    ; depth
    move.l d2,d1                    ; width
    ; InitBitMap(bm, depth, width, height) a0=bm d0=depth d1=w d2=h
    move.l d3,d2
    jsr _LVOInitBitMap(a6)

    moveq #0,d5
.gab_planes:
    cmp.l d4,d5
    bge .gab_ok
    move.l gfx_gfx_base,a6
    move.l d2,d0                    ; wait d2 was overwritten by InitBitMap height
    move.l 8(a5),d0                 ; w
    move.l 12(a5),d1                ; h
    jsr _LVOAllocRaster(a6)
    tst.l d0
    beq .gab_unwind
    lea BM_PLANES(a4),a0
    move.l d5,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l d0,(a0)
    addq.l #1,d5
    bra .gab_planes

.gab_unwind:
    ; free planes already allocated
    move.l d5,d6
.gab_uw:
    subq.l #1,d6
    bmi .gab_uw_bm
    lea BM_PLANES(a4),a0
    move.l d6,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l (a0),d0
    beq .gab_uw
    move.l gfx_gfx_base,a6
    move.l d0,a0
    move.l 8(a5),d0
    move.l 12(a5),d1
    jsr _LVOFreeRaster(a6)
    bra .gab_uw
.gab_uw_bm:
    move.l ExecBase,a6
    move.l a4,a1
    move.l #BM_SIZEOF,d0
    jsr _LVOFreeMem(a6)
    bra .gab_fail

.gab_ok:
    lea gfx_bm_ptr,a0
    move.l d7,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l a4,(a0)
    lea gfx_bm_w,a0
    move.l d7,d1
    add.l d1,d1
    adda.l d1,a0
    move.w 8+2(a5),d0               ; low word of w? better:
    move.l 8(a5),d0
    move.w d0,(a0)
    lea gfx_bm_h,a0
    move.l d7,d1
    add.l d1,d1
    adda.l d1,a0
    move.l 12(a5),d0
    move.w d0,(a0)
    lea gfx_bm_depth,a0
    move.l d7,d1
    add.l d1,d1
    adda.l d1,a0
    move.w d4,(a0)
    move.l a4,d0
    bra .gab_done
.gab_fail:
    moveq #0,d0
.gab_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

GfxFreeBitMap:
    link a6,#0
    movem.l d0-d2/a0-a1/a5,-(sp)
    move.l a6,a5
    move.l 8(a5),d0
    bsr gfx_handle_to_slot
    tst.l d0
    bmi .gfb_done
    bsr gfx_free_bm_slot
.gfb_done:
    movem.l (sp)+,d0-d2/a0-a1/a5
    unlk a6
    rts

GfxBitMapClear:
    link a6,#0
    movem.l d0-d2/a0-a1/a5-a6,-(sp)
    move.l a6,a5
    move.l 8(a5),d0
    bsr gfx_handle_to_slot
    move.l d0,d2
    bmi .gbc_done
    lea gfx_bm_ptr,a0
    move.l d2,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l (a0),a1
    move.l gfx_gfx_base,a6
    lea gfx_tmp_rp,a0
    jsr _LVOInitRastPort(a6)
    ; rp_BitMap is at offset 4 in RastPort
    lea gfx_tmp_rp,a0
    move.l a1,4(a0)
    move.l a0,a1
    moveq #0,d0
    jsr _LVOSetRast(a6)
.gbc_done:
    movem.l (sp)+,d0-d2/a0-a1/a5-a6
    unlk a6
    rts

GfxBitMapPlot:
    link a6,#0
    movem.l d0-d3/a0-a2/a5-a6,-(sp)
    move.l a6,a5
    move.l 8(a5),d0
    bsr gfx_handle_to_slot
    move.l d0,d3
    bmi .gbp_done
    lea gfx_bm_ptr,a0
    move.l d3,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l (a0),a2
    move.l gfx_gfx_base,a6
    lea gfx_tmp_rp,a0
    jsr _LVOInitRastPort(a6)
    lea gfx_tmp_rp,a0
    move.l a2,4(a0)
    move.l a0,a1
    move.l 20(a5),d0
    jsr _LVOSetAPen(a6)
    lea gfx_tmp_rp,a1
    move.l 12(a5),d0
    move.l 16(a5),d1
    jsr _LVOWritePixel(a6)
.gbp_done:
    movem.l (sp)+,d0-d3/a0-a2/a5-a6
    unlk a6
    rts

GfxBlit:
    link a6,#0
    movem.l d0-d7/a0-a2/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_rp
    beq .blit_done
    move.l 8(a5),d0
    bsr gfx_handle_to_slot
    move.l d0,d7
    bmi .blit_done
    lea gfx_bm_ptr,a0
    move.l d7,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l (a0),a0                  ; src BitMap
    move.l gfx_gfx_base,a6
    move.l 12(a5),d0                ; sx
    move.l 16(a5),d1                ; sy
    move.l gfx_rp,a1
    move.l 28(a5),d2                ; dx
    move.l 32(a5),d3                ; dy
    move.l 20(a5),d4                ; w
    move.l 24(a5),d5                ; h
    move.l #$00C0,d6                ; minterm copy
    jsr _LVOBltBitMapRastPort(a6)
.blit_done:
    movem.l (sp)+,d0-d7/a0-a2/a5-a6
    unlk a6
    rts

; =============================================================================
; Sprites
; =============================================================================
gfx_free_all_sprites:
    move.l d2,-(sp)
    moveq #0,d2
.fas:
    cmp.w #GFX_MAX_SPRITES,d2
    bge .fas_done
    move.l d2,d0
    bsr gfx_free_ss_slot
    addq.w #1,d2
    bra .fas
.fas_done:
    move.l (sp)+,d2
    rts

; d0 = slot
gfx_free_ss_slot:
    movem.l d0-d3/a0-a1/a6,-(sp)
    move.l d0,d3
    lea gfx_ss_used,a0
    move.l d3,d1
    add.l d1,d1
    adda.l d1,a0
    tst.w (a0)
    beq .fss_owned
    clr.w (a0)
    lea gfx_ss,a0
    move.l d3,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a0
    move.w SS_NUM(a0),d0
    ext.l d0
    move.l gfx_gfx_base,a6
    jsr _LVOFreeSprite(a6)
.fss_owned:
    lea gfx_ss_owned,a0
    move.l d3,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l (a0),d0
    beq .fss_clr
    move.l d0,a1
    lea gfx_ss,a0
    move.l d3,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a0
    move.w SS_HEIGHT(a0),d0
    ext.l d0
    addq.l #2,d0
    lsl.l #2,d0                     ; (height+2)*4
    move.l ExecBase,a6
    jsr _LVOFreeMem(a6)
    lea gfx_ss_owned,a0
    move.l d3,d1
    lsl.l #2,d1
    adda.l d1,a0
    clr.l (a0)
.fss_clr:
    lea gfx_ss,a0
    move.l d3,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a0
    moveq #(SS_SIZEOF/2)-1,d0
.fss_z:
    clr.w (a0)+
    dbra d0,.fss_z
    movem.l (sp)+,d0-d3/a0-a1/a6
    rts

GfxSpriteGet:
    link a6,#0
    movem.l d1-d3/a0-a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_vp
    beq .gsg_fail
    moveq #0,d2
.gsg_find:
    cmp.w #GFX_MAX_SPRITES,d2
    bge .gsg_fail
    lea gfx_ss_used,a0
    move.l d2,d1
    add.l d1,d1
    adda.l d1,a0
    tst.w (a0)
    beq .gsg_got
    addq.w #1,d2
    bra .gsg_find
.gsg_got:
    lea gfx_ss,a0
    move.l d2,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a0
    moveq #(SS_SIZEOF/2)-1,d0
.gsg_clr:
    clr.w (a0)+
    dbra d0,.gsg_clr
    lea gfx_ss,a0
    move.l d2,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a0
    move.w #1,SS_HEIGHT(a0)
    move.l gfx_gfx_base,a6
    move.l 8(a5),d0                 ; prefer
    jsr _LVOGetSprite(a6)
    tst.w d0
    bmi .gsg_fail
    lea gfx_ss_used,a0
    move.l d2,d1
    add.l d1,d1
    adda.l d1,a0
    move.w #1,(a0)
    move.l d2,d0
    bra .gsg_done
.gsg_fail:
    moveq #-1,d0
.gsg_done:
    movem.l (sp)+,d1-d3/a0-a1/a5-a6
    unlk a6
    rts

GfxSpriteData:
    link a6,#0
    movem.l d1-d7/a0-a3/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_vp
    beq .gsd_fail
    move.l 8(a5),d3                 ; slot
    bmi .gsd_fail
    cmp.l #GFX_MAX_SPRITES,d3
    bge .gsd_fail
    lea gfx_ss_used,a0
    move.l d3,d1
    add.l d1,d1
    adda.l d1,a0
    tst.w (a0)
    beq .gsd_fail
    move.l 12(a5),d4                ; data ptr
    beq .gsd_fail
    move.l 16(a5),d5                ; height
    ble .gsd_fail

    ; free previous owned
    lea gfx_ss_owned,a0
    move.l d3,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l (a0),d0
    beq .gsd_alloc
    move.l d0,a1
    lea gfx_ss,a0
    move.l d3,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a0
    move.w SS_HEIGHT(a0),d0
    ext.l d0
    addq.l #2,d0
    lsl.l #2,d0
    move.l ExecBase,a6
    jsr _LVOFreeMem(a6)
    lea gfx_ss_owned,a0
    move.l d3,d1
    lsl.l #2,d1
    adda.l d1,a0
    clr.l (a0)

.gsd_alloc:
    move.l d5,d0
    addq.l #2,d0
    lsl.l #2,d0                     ; bytes
    move.l d0,d7
    move.l ExecBase,a6
    move.l #MEMF_CHIP!MEMF_CLEAR,d1
    jsr _LVOAllocMem(a6)
    tst.l d0
    beq .gsd_fail
    move.l d0,a2
    lea gfx_ss_owned,a0
    move.l d3,d1
    lsl.l #2,d1
    adda.l d1,a0
    move.l a2,(a0)
    ; copy
    move.l d4,a0
    move.l a2,a1
    move.l d7,d0
.gsd_copy:
    move.b (a0)+,(a1)+
    subq.l #1,d0
    bne .gsd_copy

    lea gfx_ss,a0
    move.l d3,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a0
    move.w d5,SS_HEIGHT(a0)
    move.l a2,SS_POSCTLDATA(a0)
    move.l gfx_gfx_base,a6
    move.l gfx_vp,a0
    lea gfx_ss,a1
    move.l d3,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a1
    move.l a2,a2
    ; ChangeSprite(vp, sprite, data) a0=vp a1=sprite a2=data
    jsr _LVOChangeSprite(a6)
    moveq #0,d0
    bra .gsd_done
.gsd_fail:
    moveq #-1,d0
.gsd_done:
    movem.l (sp)+,d1-d7/a0-a3/a5-a6
    unlk a6
    rts

GfxSpriteMove:
    link a6,#0
    movem.l d0-d2/a0-a1/a5-a6,-(sp)
    move.l a6,a5
    tst.l gfx_vp
    beq .gsm_done
    move.l 8(a5),d2
    bmi .gsm_done
    cmp.l #GFX_MAX_SPRITES,d2
    bge .gsm_done
    lea gfx_ss_used,a0
    move.l d2,d1
    add.l d1,d1
    adda.l d1,a0
    tst.w (a0)
    beq .gsm_done
    move.l gfx_gfx_base,a6
    move.l gfx_vp,a0
    lea gfx_ss,a1
    move.l d2,d1
    mulu #SS_SIZEOF,d1
    adda.l d1,a1
    move.l 12(a5),d0
    move.l 16(a5),d1
    jsr _LVOMoveSprite(a6)
.gsm_done:
    movem.l (sp)+,d0-d2/a0-a1/a5-a6
    unlk a6
    rts

GfxSpriteFree:
    link a6,#0
    movem.l d0/a5,-(sp)
    move.l a6,a5
    move.l 8(a5),d0
    bmi .gsf_done
    cmp.l #GFX_MAX_SPRITES,d0
    bge .gsf_done
    bsr gfx_free_ss_slot
.gsf_done:
    movem.l (sp)+,d0/a5
    unlk a6
    rts

; =============================================================================
GfxWaitEvent:
    link a6,#0
    movem.l d1-d3/a0-a2/a6,-(sp)
    moveq #GFX_EVT_NONE,d3
    move.l gfx_window,d0
    beq .gwe_done
    move.l d0,a2
    move.l WD_USERPORT(a2),d0
    beq .gwe_done
    move.l d0,a0
    moveq #0,d0
    move.b MP_SIGBIT(a0),d0
    moveq #1,d1
    lsl.l d0,d1
    move.l d1,d0
    move.l ExecBase,a6
    jsr _LVOWait(a6)
.gwe_loop:
    move.l WD_USERPORT(a2),a0
    move.l ExecBase,a6
    jsr _LVOGetMsg(a6)
    tst.l d0
    beq .gwe_done
    move.l d0,a1
    move.l IM_CLASS(a1),d1
    move.w IM_CODE(a1),d2
    jsr _LVOReplyMsg(a6)
    cmp.l #IDCMP_CLOSEWINDOW,d1
    beq .gwe_close
    cmp.l #IDCMP_VANILLAKEY,d1
    bne .gwe_loop
    cmp.b #27,d2
    beq .gwe_close
    cmp.b #'q',d2
    beq .gwe_close
    cmp.b #'Q',d2
    beq .gwe_close
    bra .gwe_loop
.gwe_close:
    moveq #GFX_EVT_CLOSE,d3
.gwe_done:
    move.l d3,d0
    movem.l (sp)+,d1-d3/a0-a2/a6
    unlk a6
    rts

    end
