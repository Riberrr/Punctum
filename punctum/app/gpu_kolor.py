"""Odszumianie koloru na karcie graficznej (punkt 32).

Po co: podglad z karty nie mial odszumiania koloru, a procesor dokladal je
dopiero po chwili ciszy (ok. 0,5 s, a liczenie trwa ~190 ms - za wolno na
kazdy ruch suwaka). Kolory przeskakiwaly wiec przy kazdym zatrzymaniu
i ruszeniu suwaka - to byly "mikromigniecia". Tutaj ta sama operacja co
`core.denoise._denoise_color` liczy sie w kilka milisekund przy kazdej klatce.

Wierne odwzorowanie wersji z procesora, bo wynik ma sie nie roznic od
eksportu: przeliczenia RGB <-> YCrCb i zmiany rozmiaru odtwarzaja arytmetyke
calkowita OpenCV, falki a trous maja ten sam brzeg (REFLECT), rozmycie 9x9
swoj (REFLECT_101). Prog kazdej skali to mediana lokalnej energii - mediany
nie da sie tanio policzyc w shaderze, wiec probki (co czwarty piksel, jak
`rms[::4, ::4]`) odczytujemy jako float i mediane liczy numpy.

Wszystkie przebiegi pracuja we wspolrzednych obrazu (wiersz 0 = gora);
FBO ma os y odwrotnie, stad `piksel()` i `pobierz()`.
"""

from __future__ import annotations

import numpy as np

POZIOMY = 5  # jak _chroma_shrink(levels=5)

_GL_TEXTURE_2D = 0x0DE1
_GL_TEXTURE0 = 0x84C0
_GL_RG32F = 0x8230
_GL_RGBA32F = 0x8814

_WIERZCHOLKI = """
#version 330 core
layout(location = 0) in vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
"""

_WSPOLNE = """
#version 330 core
out vec4 o;
// Wiazanie QPoint w Qt ustawia uniform zmiennoprzecinkowy, wiec rozmiary
// przychodza jako vec2 i zamieniamy je na liczby calkowite tutaj.
uniform vec2 u_outSizeF;
#define u_outSize ivec2(u_outSizeF)
uniform int u_offX;
ivec2 piksel() {
    return ivec2(int(gl_FragCoord.x) - u_offX, u_outSize.y - 1 - int(gl_FragCoord.y));
}
vec4 pobierz(sampler2D t, ivec2 p, ivec2 size) {
    return texelFetch(t, ivec2(p.x, size.y - 1 - p.y), 0);
}
// BORDER_REFLECT: fedcba|abcdef|fedcba (tak liczy sepFilter2D w denoise.py)
int odbij(int i, int n) {
    if (n <= 1) return 0;
    for (int k = 0; k < 8 && (i < 0 || i >= n); k++) {
        if (i < 0) i = -i - 1;
        if (i >= n) i = 2 * n - i - 1;
    }
    return clamp(i, 0, n - 1);
}
// BORDER_REFLECT_101: gfedcb|abcdefgh|gfedcba (domyslny brzeg cv2.blur)
int odbij101(int i, int n) {
    if (n <= 1) return 0;
    for (int k = 0; k < 8 && (i < 0 || i >= n); k++) {
        if (i < 0) i = -i;
        if (i >= n) i = 2 * n - i - 2;
    }
    return clamp(i, 0, n - 1);
}
ivec3 rgb8(sampler2D t, ivec2 p, ivec2 size) {
    return ivec3(pobierz(t, p, size).rgb * 255.0 + 0.5);
}
// cv2.COLOR_RGB2YCrCb dla uint8: stale i zaokraglenie jak w OpenCV
int luma(ivec3 c) { return (c.r * 4899 + c.g * 9617 + c.b * 1868 + 8192) >> 14; }
ivec2 crcb(ivec3 c) {
    int y = luma(c);
    int cr = ((c.r - y) * 11682 + (128 << 14) + 8192) >> 14;
    int cb = ((c.b - y) * 9241 + (128 << 14) + 8192) >> 14;
    return clamp(ivec2(cr, cb), 0, 255);
}
"""

# cv2.resize(INTER_AREA) chromy do polowy. Przy parzystym boku to srednia
# 2x2 z zaokragleniem (suma + 2) >> 2, przy nieparzystym - wagi pol.
_POLOWA = _WSPOLNE + """
uniform sampler2D u_tone;
uniform vec2 u_toneSizeF;
#define u_toneSize ivec2(u_toneSizeF)
void main() {
    ivec2 p = piksel();
    if (u_toneSize.x == 2 * u_outSize.x && u_toneSize.y == 2 * u_outSize.y) {
        ivec2 s = crcb(rgb8(u_tone, 2 * p, u_toneSize))
                + crcb(rgb8(u_tone, 2 * p + ivec2(1, 0), u_toneSize))
                + crcb(rgb8(u_tone, 2 * p + ivec2(0, 1), u_toneSize))
                + crcb(rgb8(u_tone, 2 * p + ivec2(1, 1), u_toneSize));
        o = vec4(vec2((s + 2) >> 2), 0.0, 1.0);
        return;
    }
    vec2 skala = vec2(u_toneSize) / vec2(u_outSize);
    vec2 a = vec2(p) * skala;
    vec2 b = a + skala;
    vec2 suma = vec2(0.0);
    for (int j = int(floor(a.y)); j < int(ceil(b.y)) && j < u_toneSize.y; j++) {
        float wy = min(b.y, float(j + 1)) - max(a.y, float(j));
        for (int i = int(floor(a.x)); i < int(ceil(b.x)) && i < u_toneSize.x; i++) {
            float wx = min(b.x, float(i + 1)) - max(a.x, float(i));
            suma += wx * wy * vec2(crcb(rgb8(u_tone, ivec2(i, j), u_toneSize)));
        }
    }
    o = vec4(clamp(floor(suma / (skala.x * skala.y) + 0.5), 0.0, 255.0), 0.0, 1.0);
}
"""

# Jeden kierunek filtra a trous B3 (1 4 6 4 1)/16 z krokiem 2^poziom.
_ROZMYCIE = _WSPOLNE + """
uniform sampler2D u_src;
uniform vec2 u_kierF;
#define u_kier ivec2(u_kierF)
uniform int u_krok;
const float B3[5] = float[5](0.0625, 0.25, 0.375, 0.25, 0.0625);
void main() {
    ivec2 p = piksel();
    vec2 s = vec2(0.0);
    for (int k = 0; k < 5; k++) {
        ivec2 q = p + u_kier * (k - 2) * u_krok;
        q = ivec2(odbij(q.x, u_outSize.x), odbij(q.y, u_outSize.y));
        s += B3[k] * pobierz(u_src, q, u_outSize).rg;
    }
    o = vec4(s, 0.0, 1.0);
}
"""

# Suma poziomych 9 wartosci d^2 (pierwsza polowa cv2.blur 9x9).
_PUDELKO = _WSPOLNE + """
uniform sampler2D u_base;
uniform sampler2D u_smooth;
void main() {
    ivec2 p = piksel();
    vec2 s = vec2(0.0);
    for (int k = -4; k <= 4; k++) {
        ivec2 q = ivec2(odbij101(p.x + k, u_outSize.x), p.y);
        vec2 d = pobierz(u_base, q, u_outSize).rg - pobierz(u_smooth, q, u_outSize).rg;
        s += d * d;
    }
    o = vec4(s, 0.0, 1.0);
}
"""

# Druga polowa rozmycia i pierwiastek - tylko w punktach rms[::4, ::4].
_PROBKI = _WSPOLNE + """
uniform sampler2D u_poziomo;
uniform vec2 u_sizeF;
#define u_size ivec2(u_sizeF)
void main() {
    ivec2 p = piksel() * 4;
    vec2 s = vec2(0.0);
    for (int k = -4; k <= 4; k++) {
        ivec2 q = ivec2(p.x, odbij101(p.y + k, u_size.y));
        s += pobierz(u_poziomo, q, u_size).rg;
    }
    o = vec4(sqrt(max(s / 81.0, 0.0)), 0.0, 1.0);
}
"""

# Lagodne tlumienie kazdej skali d*d^2/(d^2+t^2) i zaokraglenie do uint8.
_SUMA = _WSPOLNE + """
uniform sampler2D u_b0;
uniform sampler2D u_b1;
uniform sampler2D u_b2;
uniform sampler2D u_b3;
uniform sampler2D u_b4;
uniform sampler2D u_b5;
uniform vec2 u_t[5];
vec2 tlum(vec2 d, vec2 t) { vec2 d2 = d * d; return d * d2 / (d2 + t * t + 1e-12); }
void main() {
    ivec2 p = piksel();
    vec2 b0 = pobierz(u_b0, p, u_outSize).rg;
    vec2 b1 = pobierz(u_b1, p, u_outSize).rg;
    vec2 b2 = pobierz(u_b2, p, u_outSize).rg;
    vec2 b3 = pobierz(u_b3, p, u_outSize).rg;
    vec2 b4 = pobierz(u_b4, p, u_outSize).rg;
    vec2 b5 = pobierz(u_b5, p, u_outSize).rg;
    vec2 wynik = tlum(b0 - b1, u_t[0]) + tlum(b1 - b2, u_t[1]) + tlum(b2 - b3, u_t[2])
               + tlum(b3 - b4, u_t[3]) + tlum(b4 - b5, u_t[4]) + b5;
    o = vec4(clamp(floor(wynik + 0.5), 0.0, 255.0), 0.0, 1.0);
}
"""

# Chroma z powrotem do pelnego rozmiaru (INTER_LINEAR, wspolczynniki
# staloprzecinkowe jak w OpenCV) i YCrCb -> RGB arytmetyka calkowita.
_SKLAD = _WSPOLNE + """
uniform sampler2D u_tone;
uniform sampler2D u_chroma;
uniform vec2 u_csizeF;
#define u_csize ivec2(u_csizeF)
void wspolczynnik(int x, int n, int m, out int i0, out int i1, out int w1) {
    float f = (float(x) + 0.5) * float(m) / float(n) - 0.5;
    int s = int(floor(f));
    f -= float(s);
    if (s < 0) { s = 0; f = 0.0; }
    if (s >= m - 1) { s = m - 1; f = 0.0; }
    i0 = s;
    i1 = min(s + 1, m - 1);
    w1 = int(f * 2048.0 + 0.5);
}
void main() {
    ivec2 p = piksel();
    ivec3 c = rgb8(u_tone, p, u_outSize);
    int y = luma(c);
    int x0, x1, ax, y0, y1, ay;
    wspolczynnik(p.x, u_outSize.x, u_csize.x, x0, x1, ax);
    wspolczynnik(p.y, u_outSize.y, u_csize.y, y0, y1, ay);
    ivec2 v00 = ivec2(pobierz(u_chroma, ivec2(x0, y0), u_csize).rg + 0.5);
    ivec2 v01 = ivec2(pobierz(u_chroma, ivec2(x1, y0), u_csize).rg + 0.5);
    ivec2 v10 = ivec2(pobierz(u_chroma, ivec2(x0, y1), u_csize).rg + 0.5);
    ivec2 v11 = ivec2(pobierz(u_chroma, ivec2(x1, y1), u_csize).rg + 0.5);
    ivec2 h0 = v00 * (2048 - ax) + v01 * ax;
    ivec2 h1 = v10 * (2048 - ax) + v11 * ax;
    ivec2 cc = clamp((h0 * (2048 - ay) + h1 * ay + (1 << 21)) >> 22, 0, 255);
    int cr = cc.x - 128;
    int cb = cc.y - 128;
    int r = y + ((cr * 22987 + 8192) >> 14);
    int g = y + ((cb * -5636 + cr * -11698 + 8192) >> 14);
    int b = y + ((cb * 29049 + 8192) >> 14);
    o = vec4(vec3(clamp(ivec3(r, g, b), 0, 255)) / 255.0, 1.0);
}
"""


# Powiekszenie gotowego wycinka ponad 1:1 - odszumianie liczy sie w skali
# natywnej (jak develop_region), dopiero potem obraz rosnie.
_SKALUJ = _WSPOLNE + """
uniform sampler2D u_src;
void main() {
    o = vec4(texture(u_src, gl_FragCoord.xy / u_outSizeF).rgb, 1.0);
}
"""


class KolorNaKarcie:
    """Przebiegi odszumiania koloru we wspolnym kontekscie GpuRenderer.

    Wolac tylko przy aktywnym kontekscie i zwiazanym VAO prostokata.
    """

    def __init__(self, context, vao):
        from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

        self._context = context
        self._vao = vao
        self._fbo: dict = {}
        self.blad = ""
        self.programy = {}
        for nazwa, zrodlo in (("polowa", _POLOWA), ("rozmycie", _ROZMYCIE),
                              ("pudelko", _PUDELKO), ("probki", _PROBKI),
                              ("suma", _SUMA), ("sklad", _SKLAD), ("skaluj", _SKALUJ)):
            program = QOpenGLShaderProgram()
            if not (program.addShaderFromSourceCode(QOpenGLShader.Vertex, _WIERZCHOLKI)
                    and program.addShaderFromSourceCode(QOpenGLShader.Fragment, zrodlo)
                    and program.link()):
                self.blad = f"{nazwa}: {program.log()}"
                self.programy = {}
                return
            self.programy[nazwa] = program

    @property
    def gotowy(self) -> bool:
        return bool(self.programy)

    def _bufor(self, klucz: str, w: int, h: int, format_: int = _GL_RG32F):
        from PySide6.QtOpenGL import QOpenGLFramebufferObject

        fbo = self._fbo.get(klucz)
        if fbo is None or fbo.width() != w or fbo.height() != h:
            fbo = QOpenGLFramebufferObject(
                w, h, QOpenGLFramebufferObject.NoAttachment, _GL_TEXTURE_2D, format_)
            self._fbo[klucz] = fbo
        return fbo

    def _przebieg(self, nazwa: str, cel, rozmiar, tekstury: dict, ustaw=None,
                  okno=None) -> None:
        """Jeden przebieg: tekstury {uniform: id}, `ustaw(program)` dla reszty."""
        from PySide6.QtGui import QVector2D

        f = self._context.functions()
        program = self.programy[nazwa]
        cel.bind()
        x0, w, h = (okno or (0, rozmiar[0], rozmiar[1]))
        f.glViewport(x0, 0, w, h)
        program.bind()
        for jednostka, (uniform, tekstura) in enumerate(tekstury.items()):
            f.glActiveTexture(_GL_TEXTURE0 + jednostka)
            f.glBindTexture(_GL_TEXTURE_2D, tekstura)
            program.setUniformValue1i(uniform, jednostka)
        program.setUniformValue("u_outSizeF", QVector2D(float(w), float(h)))
        program.setUniformValue1i("u_offX", int(x0))
        if ustaw is not None:
            ustaw(program)
        f.glDrawArrays(0x0005, 0, 4)  # GL_TRIANGLE_STRIP
        program.release()
        f.glActiveTexture(_GL_TEXTURE0)

    def odszum(self, ton_tekstura: int, w: int, h: int, sila: float):
        """Zwraca FBO (RGBA8, w x h) z odszumionym kolorem.

        `sila` jak w `_denoise_color`: suwak/100 * 16.
        """
        from PySide6.QtGui import QVector2D

        w2, h2 = max(1, w // 2), max(1, h // 2)
        self._vao.bind()

        bazy = [self._bufor("b0", w2, h2)]
        self._przebieg("polowa", bazy[0], (w2, h2), {"u_tone": ton_tekstura},
                       lambda p: p.setUniformValue("u_toneSizeF", QVector2D(w, h)))
        pomoc = self._bufor("pomoc", w2, h2)
        for j in range(POZIOMY):
            krok = 2 ** j
            self._przebieg("rozmycie", pomoc, (w2, h2), {"u_src": bazy[j].texture()},
                           lambda p, k=krok: (p.setUniformValue("u_kierF", QVector2D(1, 0)),
                                              p.setUniformValue1i("u_krok", k)))
            nastepna = self._bufor(f"b{j + 1}", w2, h2)
            self._przebieg("rozmycie", nastepna, (w2, h2), {"u_src": pomoc.texture()},
                           lambda p, k=krok: (p.setUniformValue("u_kierF", QVector2D(0, 1)),
                                              p.setUniformValue1i("u_krok", k)))
            bazy.append(nastepna)

        # probki rms[::4, ::4] wszystkich poziomow obok siebie w jednym buforze
        sw, sh = (w2 + 3) // 4, (h2 + 3) // 4
        atlas = self._bufor("atlas", sw * POZIOMY, sh, _GL_RGBA32F)
        for j in range(POZIOMY):
            self._przebieg("pudelko", pomoc, (w2, h2),
                           {"u_base": bazy[j].texture(), "u_smooth": bazy[j + 1].texture()})
            self._przebieg("probki", atlas, None, {"u_poziomo": pomoc.texture()},
                           lambda p: p.setUniformValue("u_sizeF", QVector2D(w2, h2)),
                           okno=(j * sw, sw, sh))
        obraz = atlas.toImage(False)
        dane = np.frombuffer(obraz.constBits(), dtype=np.float32,
                             count=obraz.height() * obraz.bytesPerLine() // 4).copy()
        dane = dane.reshape(obraz.height(), -1)[:, : sw * POZIOMY * 4].reshape(sh, POZIOMY, sw, 4)
        progi = [(sila * float(np.median(dane[:, j, :, 0])),
                  sila * float(np.median(dane[:, j, :, 1]))) for j in range(POZIOMY)]

        chroma = self._bufor("chroma", w2, h2)

        def ustaw_progi(p):
            for j, (tr, tb) in enumerate(progi):
                p.setUniformValue(f"u_t[{j}]", QVector2D(tr, tb))

        self._przebieg("suma", chroma, (w2, h2),
                       {f"u_b{j}": bazy[j].texture() for j in range(POZIOMY + 1)}, ustaw_progi)
        wynik = self._bufor("wynik", w, h, 0x8058)  # GL_RGBA8
        self._przebieg("sklad", wynik, (w, h),
                       {"u_tone": ton_tekstura, "u_chroma": chroma.texture()},
                       lambda p: p.setUniformValue("u_csizeF", QVector2D(w2, h2)))
        self._vao.release()
        return wynik

    def skaluj(self, zrodlo, w: int, h: int, najblizszy: bool):
        """Powieksza gotowy obraz do w x h (najblizszy sasiad albo liniowo)."""
        f = self._context.functions()
        filtr = 0x2600 if najblizszy else 0x2601  # GL_NEAREST / GL_LINEAR
        f.glBindTexture(_GL_TEXTURE_2D, zrodlo.texture())
        for nazwa in (0x2801, 0x2800):  # MIN_FILTER, MAG_FILTER
            f.glTexParameteri(_GL_TEXTURE_2D, nazwa, filtr)
        for nazwa in (0x2802, 0x2803):  # WRAP_S, WRAP_T
            f.glTexParameteri(_GL_TEXTURE_2D, nazwa, 0x812F)  # CLAMP_TO_EDGE
        f.glBindTexture(_GL_TEXTURE_2D, 0)
        cel = self._bufor("powiekszony", w, h, 0x8058)
        self._vao.bind()
        self._przebieg("skaluj", cel, (w, h), {"u_src": zrodlo.texture()})
        self._vao.release()
        return cel
