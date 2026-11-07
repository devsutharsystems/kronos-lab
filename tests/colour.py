"""Colour helpers for the site tests: sRGB contrast, CIELAB, CIEDE2000, mixing. Standard library only."""
import itertools
import math
def lin(c):
    c/=255; return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
def lab(h):
    h=h.lstrip('#'); r,g,b=[lin(int(h[i:i+2],16)) for i in (0,2,4)]
    X=(0.4124564*r+0.3575761*g+0.1804375*b)/0.95047; Y=0.2126729*r+0.7151522*g+0.0721750*b; Z=(0.0193339*r+0.1191920*g+0.9503041*b)/1.08883
    f=lambda t: t**(1/3) if t>216/24389 else (24389/27*t+16)/116
    fx,fy,fz=f(X),f(Y),f(Z); return 116*fy-16,500*(fx-fy),200*(fy-fz)
def de2000(l1,l2):
    L1,a1,b1=l1;L2,a2,b2=l2
    C1=math.hypot(a1,b1);C2=math.hypot(a2,b2);Cb=(C1+C2)/2
    G=0.5*(1-math.sqrt(Cb**7/(Cb**7+25**7)))
    a1p,a2p=(1+G)*a1,(1+G)*a2
    C1p,C2p=math.hypot(a1p,b1),math.hypot(a2p,b2)
    h1=math.degrees(math.atan2(b1,a1p))%360 if C1p else 0
    h2=math.degrees(math.atan2(b2,a2p))%360 if C2p else 0
    dL=L2-L1;dC=C2p-C1p
    if C1p*C2p==0: dh=0
    else:
        dh=h2-h1
        if dh>180: dh-=360
        elif dh<-180: dh+=360
    dH=2*math.sqrt(C1p*C2p)*math.sin(math.radians(dh/2))
    Lb=(L1+L2)/2;Cbp=(C1p+C2p)/2
    if C1p*C2p==0: hb=h1+h2
    elif abs(h1-h2)<=180: hb=(h1+h2)/2
    else: hb=(h1+h2+360)/2 if h1+h2<360 else (h1+h2-360)/2
    T=1-0.17*math.cos(math.radians(hb-30))+0.24*math.cos(math.radians(2*hb))+0.32*math.cos(math.radians(3*hb+6))-0.20*math.cos(math.radians(4*hb-63))
    dth=30*math.exp(-((hb-275)/25)**2)
    Rc=2*math.sqrt(Cbp**7/(Cbp**7+25**7))
    Sl=1+0.015*(Lb-50)**2/math.sqrt(20+(Lb-50)**2);Sc=1+0.045*Cbp;Sh=1+0.015*Cbp*T
    Rt=-math.sin(math.radians(2*dth))*Rc
    return math.sqrt((dL/Sl)**2+(dC/Sc)**2+(dH/Sh)**2+Rt*(dC/Sc)*(dH/Sh))
def lum(h):
    h=h.lstrip('#');r,g,b=[lin(int(h[i:i+2],16)) for i in (0,2,4)];return 0.2126*r+0.7152*g+0.0722*b
def cr(a,b):
    la,lb=sorted((lum(a),lum(b)),reverse=True);return (la+.05)/(lb+.05)
def table(d,bg):
    ks=list(d);m=0;worst=None;mn=1e9
    for a,b in itertools.combinations(ks,2):
        v=de2000(lab(d[a]),lab(d[b]));
        if v<mn: mn=v;worst=(a,b)
    return mn,worst


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hexs(c):
    return "#" + "".join(f"{round(v):02x}" for v in c)


def mix(a, b, pct):
    """color-mix(in srgb, a pct%, b): channel-wise blend of two hex colours (or rgb tuples)."""
    ca, cb = (rgb(a) if isinstance(a, str) else a), (rgb(b) if isinstance(b, str) else b)
    return tuple(pct / 100 * x + (1 - pct / 100) * y for x, y in zip(ca, cb))


def over(fg_rgb, alpha, bg):
    """Composite a translucent colour over an opaque hex background."""
    return mix(tuple(fg_rgb), bg, alpha * 100)


def hue_degrees(h):
    r, g, b = [v / 255 for v in rgb(h)]
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0.0
    d = mx - mn
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return hue * 60


def cr_rgb(a, b):
    f = lambda c: hexs(c) if not isinstance(c, str) else c
    return cr(f(a), f(b))


def distance_table(colours: dict) -> dict:
    return {(a, b): de2000(lab(colours[a]), lab(colours[b])) for a, b in itertools.combinations(colours, 2)}
