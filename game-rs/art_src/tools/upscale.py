"""Увеличение картинок ×4 нейросетью Real-ESRGAN (x4plus), на процессоре.
Нужно: torch (cpu) и веса RealESRGAN_x4plus.pth (github.com/xinntao/Real-ESRGAN/releases v0.1.0).
Использование: python3 upscale.py ВЕСА.pth ВХОД.png ВЫХОД.png"""
import sys, numpy as np, torch, torch.nn as nn, torch.nn.functional as F
from PIL import Image


class RDB5(nn.Module):
    def __init__(s, nf=64, gc=32):
        super().__init__()
        s.conv1 = nn.Conv2d(nf, gc, 3, 1, 1); s.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1); s.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        s.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1); s.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1); s.l = nn.LeakyReLU(0.2, True)
    def forward(s, x):
        x1 = s.l(s.conv1(x)); x2 = s.l(s.conv2(torch.cat((x, x1), 1))); x3 = s.l(s.conv3(torch.cat((x, x1, x2), 1)))
        x4 = s.l(s.conv4(torch.cat((x, x1, x2, x3), 1))); x5 = s.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(s, nf=64, gc=32):
        super().__init__(); s.rdb1 = RDB5(nf, gc); s.rdb2 = RDB5(nf, gc); s.rdb3 = RDB5(nf, gc)
    def forward(s, x): return s.rdb3(s.rdb2(s.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(s, nf=64, nb=23, gc=32):
        super().__init__()
        s.conv_first = nn.Conv2d(3, nf, 3, 1, 1); s.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)]); s.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        s.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1); s.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1); s.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1); s.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
        s.l = nn.LeakyReLU(0.2, True)
    def forward(s, x):
        f = s.conv_first(x); f = f + s.conv_body(s.body(f))
        f = s.l(s.conv_up1(F.interpolate(f, scale_factor=2, mode='nearest'))); f = s.l(s.conv_up2(F.interpolate(f, scale_factor=2, mode='nearest')))
        return s.conv_last(s.l(s.conv_hr(f)))


_net = None
def load(w):
    global _net
    _net = RRDBNet(); sd = torch.load(w, map_location='cpu'); _net.load_state_dict(sd.get('params_ema', sd.get('params', sd)), strict=True); _net.eval()
    torch.set_num_threads(4)


def up(im):
    """PIL RGB → PIL RGB ×4 (по кускам с перекрытием, чтобы хватило памяти)"""
    a = np.asarray(im.convert('RGB')).astype(np.float32) / 255; h, w, _ = a.shape; out = np.zeros((h * 4, w * 4, 3), np.float32)
    T, P = 160, 10
    with torch.no_grad():
        for y in range(0, h, T):
            for x in range(0, w, T):
                y0, x0 = max(0, y - P), max(0, x - P); y1, x1 = min(h, y + T + P), min(w, x + T + P)
                t = torch.from_numpy(a[y0:y1, x0:x1].transpose(2, 0, 1)).unsqueeze(0)
                r = _net(t).clamp(0, 1)[0].numpy().transpose(1, 2, 0)
                yy, xx = (y - y0) * 4, (x - x0) * 4; hh, ww = min(T, h - y) * 4, min(T, w - x) * 4
                out[y * 4:y * 4 + hh, x * 4:x * 4 + ww] = r[yy:yy + hh, xx:xx + ww]
    return Image.fromarray((out * 255).round().astype(np.uint8))


if __name__ == '__main__':
    load(sys.argv[1]); up(Image.open(sys.argv[2])).save(sys.argv[3])
