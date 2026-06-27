# -*- coding: utf-8 -*-
"""
MOLOKA · FÁBRICA DE FICHAS · MOTOR DE FOTOS (núcleo)
Funciones de imagen: recorte + montajes (neón, regla, portada) + control de calidad.
Calibrado para Funko Pop estándar (~10 cm) sobre fondo blanco de Keepa.
"""
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from scipy import ndimage

# ---------- RECORTE (IA: rembg / U²-Net, como Canva) ----------
_rembg_session = None
def _get_rembg():
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session
        _rembg_session = new_session('u2net')   # se descarga la 1ª vez (~170MB)
    return _rembg_session

def recortar(fig_rgb):
    """Recibe PIL RGB sobre fondo blanco. Devuelve PIL RGBA recortada y limpia.
    Usa IA (rembg). Si rembg no está disponible, cae al recorte clásico."""
    try:
        from rembg import remove
        rgb = fig_rgb.convert('RGB')
        out = remove(rgb, session=_get_rembg()).convert('RGBA')
        arr = np.array(out)
        alpha = arr[:,:,3]
        solido = alpha >= 128
        # RELLENAR SOLO HUECOS PEQUEÑOS (corbata, centro de peana): agujeros internos
        # rodeados de figura y de área pequeña. Los grandes (espacio entre piernas) se
        # respetan como fondo. Umbral = 1.5% del área de la figura.
        filled = ndimage.binary_fill_holes(solido)
        huecos = filled & ~solido
        hl, hn = ndimage.label(huecos)
        area_fig = max(1, int(solido.sum()))
        umbral = int(0.015 * area_fig)
        rellenar = np.zeros_like(solido)
        for i in range(1, hn + 1):
            reg = (hl == i)
            if int(reg.sum()) < umbral:
                rellenar |= reg
        mask = solido | rellenar
        alpha = np.where(mask, 255, 0).astype(np.uint8)
        # limpiar motas: quedarse con el componente grande de la máscara
        solid = alpha > 128
        lbl, n = ndimage.label(solid)
        if n > 1:
            sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n+1))
            keep = int(np.argmax(sizes)) + 1
            alpha = np.where(lbl == keep, alpha, 0).astype(np.uint8)
        # suavizado leve del borde
        alpha = np.array(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(0.6)))
        # descontaminar halo blanco del borde (unmultiply sobre blanco)
        rgbf = np.array(rgb).astype(float)
        af = alpha.astype(float)/255.0; a3 = af[...,None]
        fg = np.clip((rgbf-(1-a3)*255.0)/np.clip(a3,0.25,1),0,255)
        arr2 = np.where((af<0.999)[...,None], fg, rgbf).astype(np.uint8)
        res = Image.fromarray(np.dstack([arr2, alpha]), 'RGBA')
        bb = Image.fromarray(alpha).getbbox()
        return res.crop(bb) if bb else res
    except Exception as e:
        print(f"   (aviso: rembg no disponible, uso recorte clásico: {e})")
        return _recortar_clasico(fig_rgb)

# ---------- RECORTE CLÁSICO (red de seguridad si la IA fallara) ----------
def _recortar_clasico(fig_rgb):
    """Recibe PIL RGB sobre fondo blanco. Devuelve PIL RGBA recortada y limpia."""
    arr = np.array(fig_rgb.convert('RGB'))
    white = (arr[:,:,0]>=235)&(arr[:,:,1]>=235)&(arr[:,:,2]>=235)
    lbl,n = ndimage.label(white)
    border = set(lbl[0,:])|set(lbl[-1,:])|set(lbl[:,0])|set(lbl[:,-1]); border.discard(0)
    bg_border = np.isin(lbl, list(border)); counts = np.bincount(lbl.ravel())
    ys,_ = np.where(~bg_border); y0,y1 = ys.min(),ys.max(); neck_y = y0+0.58*(y1-y0)
    fondo = bg_border.copy()
    big = [i for i in range(1,n+1) if counts[i]>150 and i not in border]
    if big:
        for li,com in zip(big, ndimage.center_of_mass(np.ones_like(lbl),lbl,big)):
            if com[0] < neck_y: fondo |= (lbl==li)        # axilas/cuello arriba -> fondo
    figura = ~fondo
    # rellenar huecos de TEJIDO del vestido (no blanco puro), no el cuello
    filled = ndimage.binary_fill_holes(figura); holes = filled & ~figura
    hl,hn = ndimage.label(holes)
    fillthese=[]
    for i in range(1,hn+1):
        reg=(hl==i)
        if reg.sum()<3000 and arr[reg].mean(0).min()<244: fillthese.append(i)
    figura = figura | np.isin(hl, fillthese)
    alpha = (figura*255).astype(np.uint8)
    # picos claros del cuello -> transparentar (distinguir de piel por desaturación)
    rgb=arr.astype(int); a=alpha.astype(float); Hf=a.shape[0]
    solid=a>=180; width=solid.sum(1)
    yA,yB=int(0.40*Hf),int(0.62*Hf); neck_row=yA+int(np.argmin(width[yA:yB]))
    band=np.zeros_like(solid); band[max(0,neck_row-40):neck_row+40,:]=True
    target=band&(a>=120)&(rgb.min(2)>=205)&((rgb.max(2)-rgb.min(2))<28)
    target=ndimage.binary_dilation(target,iterations=2); a[target]=0
    alpha=np.array(Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.MinFilter(3)))
    alpha=np.array(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(0.7)))
    # descontaminar borde (quitar blanco pegado)
    af=alpha.astype(float)/255.0; a3=af[...,None]
    fg=np.clip((arr.astype(float)-(1-a3)*255.0)/np.clip(a3,0.25,1),0,255)
    arr2=np.where((af<0.999)[...,None],fg,arr.astype(float)).astype(np.uint8)
    out=Image.fromarray(np.dstack([arr2,alpha]),'RGBA')
    return out.crop(Image.fromarray(alpha).getbbox())

# ---------- CONTROL DE CALIDAD (test del magenta) ----------
def test_calidad(fig_rgba):
    """Con recorte por IA, los blancos son legítimos (trajes/sombreros blancos), no suciedad.
    Solo rechazamos recortes vacíos o degenerados (si la IA fallara del todo)."""
    arr = np.array(fig_rgba); a = arr[:,:,3]
    solido = int((a >= 200).sum())
    if solido < 500:
        return False, "recorte casi vacío (la IA no encontró figura)"
    return True, "ok"

# ---------- MONTAJE FICHA M7 (header de marca + figura + datos) ----------
import re as _re, glob as _glob
_BR = [(236,72,153),(124,58,237),(34,211,238)]   # marca: #ec4899 -> #7c3aed(52%) -> #22d3ee
_STOPS = [0.0, 0.52, 1.0]
def _m7_font(sz, bold=True):
    for c in (['SpaceGrotesk-Bold.ttf'] if bold else ['SpaceGrotesk-Medium.ttf']):
        try: return ImageFont.truetype(c, sz)
        except Exception: pass
    pat = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    g = _glob.glob('/usr/share/fonts/**/'+pat, recursive=True)
    return ImageFont.truetype(g[0], sz) if g else ImageFont.load_default()
def _m7_grad(w,h,horizontal=True):
    a=np.zeros((h,w,3),np.uint8); n=(w if horizontal else h)
    for i in range(n):
        t=i/max(1,n-1); col=list(_BR[-1])
        for k in range(len(_STOPS)-1):
            if t<=_STOPS[k+1] or k==len(_STOPS)-2:
                u=(t-_STOPS[k])/max(1e-6,(_STOPS[k+1]-_STOPS[k])); u=min(max(u,0),1)
                col=[int(_BR[k][j]+(_BR[k+1][j]-_BR[k][j])*u) for j in range(3)]; break
        if horizontal: a[:,i]=col
        else: a[i,:]=col
    return Image.fromarray(a)
def _m7_tgrad(txt,font):
    tmp=Image.new('RGBA',(10,10)); d=ImageDraw.Draw(tmp); bb=d.textbbox((0,0),txt,font=font)
    w,h=bb[2]-bb[0],bb[3]-bb[1]; pad=10; W,H=w+pad*2,h+pad*2
    m=Image.new('L',(W,H),0); ImageDraw.Draw(m).text((pad-bb[0],pad-bb[1]),txt,font=font,fill=255)
    o=Image.new('RGBA',(W,H),(0,0,0,0)); o.paste(_m7_grad(W,H),(0,0),m); return o
def montar_m7(fig_rgba, f, S=1024):
    """Ficha M7: header de marca (serie+nombre+numero) + figura recortada + datos + MOLOKA.
    Sustituye a neon y regla. Recibe la figura YA recortada (RGBA) y la fila f (dict)."""
    nombre = (f.get('nombre_corto') or f.get('web_titulo') or '') if isinstance(f, dict) else str(f or '')
    fandom = (f.get('fandom') or '') if isinstance(f, dict) else ''
    mm = _re.search(r'#\s*(\d+)', nombre)
    numero = ('#'+mm.group(1)) if mm else ''
    # Nombre del personaje = nombre completo SIN el #numero (ya NO separamos coletillas).
    personaje = _re.sub(r'#\s*\d+','',nombre).strip().rstrip('|-/ ').strip() or nombre
    _fmt = (f.get('formato') or '').strip() if isinstance(f, dict) else ''
    _SEP = ' \u00b7 '
    if _fmt in ('', 'Funko Pop!'):
        pie = _SEP.join(['Funko Pop!', 'Vinilo', '\u2248 10 cm'])
    elif _fmt == 'Bitty Pop':
        pie = _SEP.join(['Funko Bitty Pop!', 'Vinilo', '\u2248 2,5 cm'])
    elif _fmt == 'Llavero':
        pie = _SEP.join(['Funko Pop! Keychain', 'Llavero'])
    elif _fmt == 'Deluxe':
        pie = _SEP.join(['Funko Pop! Deluxe', 'Vinilo'])
    else:
        pie = _SEP.join(['Funko Pop!', 'Vinilo'])
    W=S; M=Image.new('RGBA',(W,W),(255,255,255,255)); d=ImageDraw.Draw(M)
    HH=int(W*0.146); M.paste(_m7_grad(W,HH),(0,0))
    def _ancho(txt, font): bb=d.textbbox((0,0),txt,font=font); return bb[2]-bb[0]
    def _fit(txt, sz0, sz_min, x0, x_lim):
        sz=sz0
        while sz>sz_min and x0+_ancho(txt,_m7_font(sz))>x_lim: sz-=2
        return _m7_font(sz)
    # Numero de coleccion a la DERECHA (a la altura de la franquicia)
    lim_der = W-60
    if numero:
        fnum=_m7_font(44); d.text((W-60,int(HH*0.30)), numero, font=fnum, fill=(255,255,255), anchor='rm')
        lim_der=(W-60)-_ancho(numero,fnum)-24
    # FRANQUICIA grande ARRIBA (protagonista); se ajusta sola SOLO si fuera larguisima.
    if fandom:
        fr=' '.join(fandom.upper().split())
        d.text((58,int(HH*0.14)), fr, font=_fit(fr,44,30,58,lim_der), fill=(255,255,255))
    # NOMBRE del personaje, mediano, DEBAJO (ancho completo; nunca rompe por largo que sea).
    d.text((58,int(HH*0.60)), personaje, font=_fit(personaje,28,20,58,W-60), fill=(255,255,255))
    alto=int(W*0.55); r=alto/max(1,fig_rgba.height)
    fig=fig_rgba.resize((max(1,int(fig_rgba.width*r)),alto),Image.LANCZOS)
    cx=W//2; eb=int(W*0.83)
    s=Image.new('RGBA',(W,W),(0,0,0,0)); ImageDraw.Draw(s).ellipse([cx-115,eb-18,cx+115,eb+18],fill=(40,30,60,55))
    M.alpha_composite(s.filter(ImageFilter.GaussianBlur(17)))
    M.alpha_composite(fig,(cx-fig.width//2,eb-alto))
    d.line([60,int(W*0.9),W-60,int(W*0.9)],fill=(232,233,240),width=2)
    d.text((60,int(W*0.93)), pie, font=_m7_font(23,False), fill=(110,110,130))
    lg=_m7_tgrad('MOLOKA',_m7_font(56)); sc=0.52; lg=lg.resize((int(lg.width*sc),int(lg.height*sc)))
    M.paste(lg,(W-60-lg.width,int(W*0.925)),lg)
    return M.convert('RGB')

# ---------- MONTAJE NEÓN ----------
def montar_neon(fig_rgba, fondo_rgb):
    bg=fondo_rgb.convert('RGBA'); W,H=bg.size
    th=int(H*0.62); r=th/fig_rgba.height
    f2=fig_rgba.resize((int(fig_rgba.width*r),th),Image.LANCZOS)
    arr=np.array(f2).astype(float); a=arr[:,:,3]/255.0
    dist=ndimage.distance_transform_edt(a>0.5); fade=np.clip(dist/6.0,0,1)*0.45+0.55
    for c in range(3): arr[:,:,c]*=fade
    arr[:,:,3]=np.array(Image.fromarray((a*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.9)))
    f2b=Image.fromarray(np.clip(arr,0,255).astype(np.uint8),'RGBA')
    x=(W-f2b.width)//2; ground=int(H*0.90); y=ground-f2b.height; canvas=bg.copy()
    am=f2b.split()[3]; hm=am.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(13))
    hcl=Image.new('RGBA',f2b.size,(170,80,255,255)); hcl.putalpha(hm.point(lambda v:int(v*0.42)))
    h_=Image.new('RGBA',(W,H),(0,0,0,0)); h_.alpha_composite(hcl,(x,y)); canvas=Image.alpha_composite(canvas,h_)
    shd=Image.new('RGBA',(W,H),(0,0,0,0)); sd=ImageDraw.Draw(shd)
    sw,sh=int(f2b.width*0.78),int(f2b.width*0.13); cx=x+f2b.width//2
    sd.ellipse([cx-sw//2,ground-sh//2-int(sh*0.1),cx+sw//2,ground+sh//2-int(sh*0.1)],fill=(0,0,0,135))
    canvas=Image.alpha_composite(canvas,shd.filter(ImageFilter.GaussianBlur(13)))
    rf=f2b.transpose(Image.FLIP_TOP_BOTTOM); g=np.zeros((rf.height,rf.width),np.uint8)
    for yy in range(rf.height): g[yy,:]=int(60*(1-yy/rf.height))
    ra=np.minimum(np.array(rf.split()[3]),g).astype(np.uint8); rf.putalpha(Image.fromarray(ra))
    canvas.alpha_composite(rf.filter(ImageFilter.GaussianBlur(1.3)),(x,ground-2))
    canvas.alpha_composite(f2b,(x,y))
    return canvas.convert('RGB')

# ---------- MONTAJE REGLA 10 cm ----------
def montar_regla(fig_rgba, regla_rgb):
    reg=regla_rgb.convert('RGB'); W,H=reg.size; a=np.array(reg)
    R,G,B=a[:,:,0].astype(int),a[:,:,1].astype(int),a[:,:,2].astype(int)
    rosa=(R>200)&(G<150)&(B>150)&(R-G>80)
    col=rosa[:,330:376].sum(1); yy=np.where(col>3)[0]; y10,y0=int(yy.min()),int(yy.max())
    alto=y0-y10; r=alto/fig_rgba.height
    f=fig_rgba.resize((int(fig_rgba.width*r),alto),Image.LANCZOS)
    arr=np.array(f).astype(float); al=arr[:,:,3]/255.0
    dist=ndimage.distance_transform_edt(al>0.5); fade=np.clip(dist/5.0,0,1)*0.45+0.55
    for c in range(3): arr[:,:,c]*=fade
    arr[:,:,3]=np.array(Image.fromarray((al*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)))
    fb=Image.fromarray(np.clip(arr,0,255).astype(np.uint8),'RGBA')
    canvas=reg.convert('RGBA'); hueco=int((400+W)/2); x=hueco-fb.width//2; y=y0-fb.height
    shd=Image.new('RGBA',(W,H),(0,0,0,0)); sd=ImageDraw.Draw(shd)
    sw,sh=int(fb.width*0.7),int(fb.width*0.10); cx=x+fb.width//2
    sd.ellipse([cx-sw//2,y0-sh//2,cx+sw//2,y0+sh//2],fill=(0,0,0,120))
    canvas=Image.alpha_composite(canvas,shd.filter(ImageFilter.GaussianBlur(8)))
    canvas.alpha_composite(fb,(x,y))
    return canvas.convert('RGB')

# ---------- MONTAJE PORTADA (caja + figura, SIN solaparse) ----------
def montar_portada(caja_rgb, fig_rgb, S=1400):
    def rec(img,u=238):
        a=np.array(img.convert('RGB')); nf=~((a[:,:,0]>=u)&(a[:,:,1]>=u)&(a[:,:,2]>=u))
        ys,xs=np.where(nf); return img.crop((xs.min(),ys.min(),xs.max(),ys.max()))
    caja=rec(caja_rgb); fig=rec(fig_rgb)
    L=Image.new('RGB',(S,S),(255,255,255))
    def esc(img,h):
        r=h/img.height; return img.resize((max(1,int(img.width*r)),max(1,int(h))),Image.LANCZOS)
    # Alturas objetivo: figura algo mayor que la caja (da profundidad sin taparla).
    funko_h=int(0.60*S); caja_h=int(funko_h/1.12)
    cR=esc(caja,caja_h); fR=esc(fig,funko_h)
    # Margenes y hueco garantizado entre caja (izquierda) y figura (derecha).
    margen=int(0.045*S); gap=int(0.03*S)
    ancho_util=S-2*margen-gap
    # Si juntas no caben a lo ancho (figura ancha, p.ej. Goku con baculo), encoger AMBAS.
    if cR.width+fR.width > ancho_util:
        f=ancho_util/(cR.width+fR.width)
        cR=esc(cR,int(cR.height*f)); fR=esc(fR,int(fR.height*f))
    # Colocar: caja arriba-izquierda, figura abajo-derecha, sin pisarse.
    cx=margen; cy=int(0.10*S)
    fx=S-margen-fR.width
    fy=int(0.93*S)-fR.height
    # Seguro anti-solape: el borde izq. de la figura nunca invade la caja + hueco.
    if fx < cx+cR.width+gap:
        fx=cx+cR.width+gap
    L.paste(cR,(cx,cy))
    L.paste(fR,(fx,fy))
    return L


# ---------- MONTAJE PROTECTOR (caja + protector lado a lado, "Better Together") ----------
def montar_protector(caja_rgb, prot_rgb):
    """Caja del Funko (izq) + protector vacío (der), sobre blanco. El protector ya viene enderezado.
    Receta verbatim de motor_protector_colab.py."""
    def _rec(img, umbral=243, margen=4):
        g = img.convert('L'); mask = g.point(lambda p: 255 if p < umbral else 0)
        bb = mask.getbbox()
        if not bb: return img
        l,t,r,b = bb
        return img.crop((max(0,l-margen),max(0,t-margen),min(img.width,r+margen),min(img.height,b+margen)))
    def _esc(img, alto):
        return img.resize((max(1,int(img.width*alto/img.height)), alto), Image.LANCZOS)
    caja_s = _esc(_rec(caja_rgb), 820)
    prot_s = _esc(prot_rgb, 880)
    GAP, MH, MV = 40, 110, 95
    W = caja_s.width + prot_s.width + GAP + 2*MH
    H = max(caja_s.height, prot_s.height) + 2*MV
    c = Image.new('RGB', (W, H), 'white')
    by = H - MV
    c.paste(caja_s, (MH, by - caja_s.height))
    c.paste(prot_s, (MH + caja_s.width + GAP, by - prot_s.height))
    return c
