"""Tor tonalny liczony na karcie graficznej.

Powod istnienia tego modulu jest jeden: numpy potrzebuje okolo 700 ms na
przeliczenie podgladu 20-megapikselowego zdjecia, a suwak ma reagowac ponizej
16 ms. Roznica jest dwa rzedy wielkosci, wiec zadna optymalizacja kodu
w Pythonie tego nie zalatwi - trzeba zmienic maszyne liczaca.

Kluczowa obserwacja: dane RAW wgrywamy do pamieci karty RAZ, przy otwarciu
zdjecia. Kazdy ruch suwaka to potem tylko podmiana kilkunastu liczb (uniformow)
i ponowne narysowanie prostokata. Geometria - obrot, kadr, powiekszenie -
siedzi w jednej macierzy przeksztalcajacej wspolrzedne tekstury, wiec te
operacje tez sa darmowe.

Matematyka w shaderze jest dokladnie tym samym, co w `pipeline.py`. Zgodnosc
obu torow pilnuje `tools/test_gpu_zgodnosc.py` - bez tego latwo o sytuacje,
w ktorej podglad wyglada inaczej niz wyeksportowany plik.
"""

from __future__ import annotations

import numpy as np

from ..core import EditParams, RawImage
from ..core import whitebalance as wb
from ..core.geometry import output_to_source
from ..core.hardware import GpuInfo

VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 a_pos;
uniform vec2 u_outSize;
out vec2 v_pixel;
void main() {
    gl_Position = vec4(a_pos, 0.0, 1.0);
    vec2 unit = a_pos * 0.5 + 0.5;
    // Dwie rzeczy naraz.  Po pierwsze y liczymy od gory, bo taki uklad ma
    // obraz, a FBO ma odwrotny.  Po drugie odejmujemy pol piksela: srodek
    // fragmentu wypada na indeksie + 0.5, a macierz przeksztalcenia pracuje
    // w konwencji OpenCV, gdzie liczba calkowita to SRODEK piksela.  Bez tego
    // caly obraz jest przesuniety o pol piksela wzgledem toru numpy.
    v_pixel = vec2(unit.x * u_outSize.x - 0.5, (1.0 - unit.y) * u_outSize.y - 0.5);
}
"""

FRAGMENT_SHADER = """
#version 330 core
in vec2 v_pixel;
out vec4 fragColor;

uniform sampler2D u_image;
uniform vec2  u_srcSize;
// Macierze podajemy wierszami jako vec3.  Wiazania PySide6 wywracaja proces
// naruszeniem ochrony pamieci przy probie ustawienia uniformu typu mat3
// przez QMatrix3x3, a taka awaria nie zostawia zadnego sladu w Pythonie.
uniform vec3  u_srcRow0;      // piksel wyniku -> piksel zrodla, wiersz X
uniform vec3  u_srcRow1;      // ten sam, wiersz Y
uniform vec3  u_wbGain;
uniform vec3  u_camRow0;      // RGB aparatu -> liniowy sRGB
uniform vec3  u_camRow1;
uniform vec3  u_camRow2;
uniform float u_exposure;
uniform float u_contrast;
uniform float u_highlights;
uniform float u_shadows;
uniform float u_whites;
uniform float u_blacks;
uniform float u_vibrance;
uniform float u_saturation;

const float MID = 0.18;
const vec3  LUMA = vec3(0.2126, 0.7152, 0.0722);

float ramp(float e0, float e1, float x) {
    float t = clamp((x - e0) / (e1 - e0), 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}

void main() {
    vec3 position = vec3(v_pixel, 1.0);
    vec2 source = vec2(dot(u_srcRow0, position), dot(u_srcRow1, position));
    vec3 c = texture(u_image, (source + 0.5) / u_srcSize).rgb;

    // --- kolor -------------------------------------------------------
    c *= u_wbGain;
    c = vec3(dot(u_camRow0, c), dot(u_camRow1, c), dot(u_camRow2, c));
    c *= exp2(u_exposure);

    // --- swiatla i cienie, maski w dzialkach EV ----------------------
    if (u_highlights != 0.0 || u_shadows != 0.0) {
        float ev = log2(max(dot(c, LUMA), 1e-6) / MID);
        float gain = 1.0;
        if (u_shadows != 0.0) {
            gain *= 1.0 + (u_shadows / 100.0) * (1.0 - ramp(-4.5, -0.5, ev)) * 1.2;
        }
        if (u_highlights != 0.0) {
            gain *= 1.0 + (u_highlights / 100.0) * ramp(-0.2, 2.5, ev) * 0.9;
        }
        c *= gain;
    }

    // --- biele i czernie ---------------------------------------------
    if (u_blacks != 0.0) {
        float offset = -(u_blacks / 100.0) * 0.04;
        c = (c - offset) / (1.0 - offset);
    }
    if (u_whites != 0.0) {
        float evw = log2(max(dot(c, LUMA), 1e-6) / MID);
        c *= 1.0 + (u_whites / 100.0) * ramp(0.5, 3.0, evw) * 0.8;
    }

    // --- kontrast wokol szarosci 18% ---------------------------------
    if (u_contrast != 0.0) {
        float e = 1.0 + 0.6 * (u_contrast / 100.0);
        c = MID * pow(max(c, 0.0) / MID + 1e-6, vec3(e));
    }

    // --- krzywa sRGB --------------------------------------------------
    c = clamp(c, 0.0, 1.0);
    vec3 low = c * 12.92;
    vec3 high = 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055;
    c = mix(low, high, step(vec3(0.0031308), c));

    // --- nasycenie i jaskrawosc, juz po krzywej ----------------------
    if (u_saturation != 0.0 || u_vibrance != 0.0) {
        float l = dot(c, LUMA);
        c = l + (c - l) * (1.0 + u_saturation / 100.0);
        if (u_vibrance != 0.0) {
            float mx = max(max(c.r, c.g), c.b);
            float mn = min(min(c.r, c.g), c.b);
            float weight = 1.0 - clamp((mx - mn) / max(mx, 1e-6), 0.0, 1.0);
            float vib = (1.0 + (u_vibrance / 100.0) * 0.8) * weight + (1.0 - weight);
            float l2 = dot(c, LUMA);
            c = l2 + (c - l2) * vib;
        }
    }

    fragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""


def white_balance_gain(raw: RawImage, p: EditParams) -> np.ndarray:
    """Mnozniki kanalow wzgledem nastawy z aparatu."""
    if p.temperature is None and abs(p.tint) < 1e-9:
        return np.ones(3, dtype=np.float32)
    temp = p.temperature if p.temperature is not None else raw.as_shot_temp
    target = wb.camera_multipliers(raw.cam_xyz, temp, raw.as_shot_tint + p.tint)
    return (target / raw.as_shot_mult).astype(np.float32)


class GpuRenderer:
    """Renderer offscreen. Przy braku OpenGL zglasza `available == False`."""

    def __init__(self):
        self._context = None
        self._surface = None
        self._program = None
        self._vao = None
        self._vbo = None
        self._texture = None
        self._fbo = None
        self._source_size = (0, 0)
        self._error = ""
        self._ready = self._initialise()

    # ------------------------------------------------------------ start

    def _initialise(self) -> bool:
        try:
            from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
            from PySide6.QtOpenGL import (
                QOpenGLBuffer,
                QOpenGLShader,
                QOpenGLShaderProgram,
                QOpenGLVertexArrayObject,
            )
        except ImportError as exc:
            self._error = f"brak modułów OpenGL: {exc}"
            return False

        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setRenderableType(QSurfaceFormat.OpenGL)

        self._surface = QOffscreenSurface()
        self._surface.setFormat(fmt)
        self._surface.create()
        if not self._surface.isValid():
            self._error = "nie udało się utworzyć powierzchni offscreen"
            return False

        self._context = QOpenGLContext()
        self._context.setFormat(fmt)
        if not self._context.create() or not self._context.makeCurrent(self._surface):
            self._error = "nie udało się utworzyć kontekstu OpenGL 3.3"
            return False

        program = QOpenGLShaderProgram()
        if not program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX_SHADER):
            self._error = f"shader wierzchołków: {program.log()}"
            return False
        if not program.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT_SHADER):
            self._error = f"shader fragmentów: {program.log()}"
            return False
        if not program.link():
            self._error = f"konsolidacja shaderów: {program.log()}"
            return False
        self._program = program

        # prostokat na cala powierzchnie, rysowany jako pas trojkatow
        self._vao = QOpenGLVertexArrayObject()
        self._vao.create()
        self._vao.bind()
        vertices = np.array(
            [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype=np.float32
        )
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self._vbo.create()
        self._vbo.bind()
        self._vbo.allocate(vertices.tobytes(), vertices.nbytes)
        program.bind()
        program.enableAttributeArray(0)
        program.setAttributeBuffer(0, 0x1406, 0, 2, 0)  # 0x1406 = GL_FLOAT
        program.release()
        self._vbo.release()
        self._vao.release()

        self._renderer_name = self._describe_hardware()
        self._context.doneCurrent()
        return True

    def _gl_string(self, constant: int) -> str:
        try:
            value = self._context.functions().glGetString(constant)
            return value.decode(errors="replace") if isinstance(value, bytes) else str(value)
        except Exception:
            return ""

    def _describe_hardware(self) -> str:
        return self._gl_string(0x1F01) or "nieznana"  # GL_RENDERER

    def describe(self) -> GpuInfo:
        """Dane karty odczytane prosto z kontekstu OpenGL."""
        if not self._ready:
            return GpuInfo(available=False, problem=self._error or "OpenGL niedostępny")

        current = self._context.makeCurrent(self._surface)
        try:
            info = GpuInfo(
                name=self._gl_string(0x1F01) or "nieznana",  # GL_RENDERER
                vendor=self._gl_string(0x1F00),  # GL_VENDOR
                driver=self._gl_string(0x1F02),  # GL_VERSION
                glsl=self._gl_string(0x8B8C),  # GL_SHADING_LANGUAGE_VERSION
                available=True,
            )
            # Pamiec karty nie ma standardowego zapytania w OpenGL - kazdy
            # producent dodal wlasne rozszerzenie. Probujemy obu i godzimy sie
            # z zerem, gdy zadne nie odpowie.
            for constant in (0x9047, 0x87FC):  # NVIDIA, AMD; wynik w kilobajtach
                try:
                    value = self._context.functions().glGetIntegerv(constant)
                    amount = int(value[0] if isinstance(value, (list, tuple)) else value)
                    if amount > 0:
                        info.memory_mb = amount // 1024
                        break
                except Exception:
                    continue
            return info
        finally:
            if current:
                self._context.doneCurrent()

    @property
    def available(self) -> bool:
        return self._ready

    @property
    def error(self) -> str:
        return self._error

    @property
    def hardware(self) -> str:
        return getattr(self, "_renderer_name", "nieznana")

    # ------------------------------------------------------------ dane

    def set_source(self, camera_linear: np.ndarray) -> bool:
        """Wgrywa dane RAW do pamieci karty. Wywolywane raz na zdjecie."""
        if not self._ready:
            return False
        from PySide6.QtOpenGL import QOpenGLTexture

        if not self._context.makeCurrent(self._surface):
            return False
        try:
            if self._texture is not None:
                self._texture.destroy()
            height, width = camera_linear.shape[:2]
            data = np.ascontiguousarray(camera_linear, dtype=np.float32)

            texture = QOpenGLTexture(QOpenGLTexture.Target2D)
            texture.setFormat(QOpenGLTexture.RGB32F)
            texture.setSize(width, height)
            # Mipmapy sa tu konieczne, nie ozdobne: ten sam obraz ogladamy raz
            # dopasowany do okna (pomniejszenie ponad trzykrotne), raz w skali
            # 1:1. Bez nich pomniejszanie probkuje co trzeci piksel i widac
            # migotanie na drobnych strukturach.
            texture.setMipLevels(texture.maximumMipLevels())
            texture.setMinificationFilter(QOpenGLTexture.LinearMipMapLinear)
            texture.setMagnificationFilter(QOpenGLTexture.Linear)
            texture.setWrapMode(QOpenGLTexture.ClampToEdge)
            texture.allocateStorage()
            texture.setData(QOpenGLTexture.RGB, QOpenGLTexture.Float32, data.tobytes())
            texture.generateMipMaps()

            self._texture = texture
            self._source_size = (width, height)
            return True
        except Exception as exc:
            self._error = f"wgranie tekstury: {exc}"
            return False
        finally:
            self._context.doneCurrent()

    def release_source(self) -> None:
        if self._ready and self._texture is not None:
            if self._context.makeCurrent(self._surface):
                self._texture.destroy()
                self._context.doneCurrent()
            self._texture = None

    # --------------------------------------------------------- render

    def _ensure_fbo(self, width: int, height: int):
        from PySide6.QtOpenGL import QOpenGLFramebufferObject

        if self._fbo is None or self._fbo.width() != width or self._fbo.height() != height:
            if self._fbo is not None:
                self._fbo.release()
            self._fbo = QOpenGLFramebufferObject(width, height)
        return self._fbo

    def render(
        self,
        raw: RawImage,
        p: EditParams,
        out_width: int,
        out_height: int,
        region: tuple[int, int, int, int] | None = None,
        scale: float = 1.0,
        nearest: bool = False,
    ) -> np.ndarray | None:
        """Zwraca obraz RGB uint8 albo None, jesli karta nie jest dostepna.

        `nearest` przelacza powiekszanie na najblizszego sasiada - przy duzym
        zblizeniu chcemy widziec prawdziwe piksele, a nie ich interpolacje.
        """
        if not self._ready or self._texture is None:
            return None
        if not self._context.makeCurrent(self._surface):
            return None

        try:
            from PySide6.QtGui import QVector2D, QVector3D
            from PySide6.QtOpenGL import QOpenGLTexture

            self._texture.setMagnificationFilter(
                QOpenGLTexture.Nearest if nearest else QOpenGLTexture.Linear
            )
            src_w, src_h = self._source_size
            transform = output_to_source(p, src_w, src_h, region=region, scale=scale)
            cam = np.asarray(raw.cam_to_srgb, dtype=np.float64)

            fbo = self._ensure_fbo(int(out_width), int(out_height))
            fbo.bind()
            functions = self._context.functions()
            functions.glViewport(0, 0, int(out_width), int(out_height))
            functions.glDisable(0x0BE2)  # GL_BLEND
            functions.glDisable(0x0B71)  # GL_DEPTH_TEST

            program = self._program
            program.bind()
            self._vao.bind()
            self._texture.bind(0)

            def row(values) -> "QVector3D":
                return QVector3D(float(values[0]), float(values[1]), float(values[2]))

            program.setUniformValue1i("u_image", 0)
            program.setUniformValue("u_outSize", QVector2D(float(out_width), float(out_height)))
            program.setUniformValue("u_srcSize", QVector2D(float(src_w), float(src_h)))
            program.setUniformValue("u_srcRow0", row(transform[0]))
            program.setUniformValue("u_srcRow1", row(transform[1]))
            program.setUniformValue("u_camRow0", row(cam[0]))
            program.setUniformValue("u_camRow1", row(cam[1]))
            program.setUniformValue("u_camRow2", row(cam[2]))
            program.setUniformValue("u_wbGain", row(white_balance_gain(raw, p)))

            for name, value in (
                ("u_exposure", p.exposure),
                ("u_contrast", p.contrast),
                ("u_highlights", p.highlights),
                ("u_shadows", p.shadows),
                ("u_whites", p.whites),
                ("u_blacks", p.blacks),
                ("u_vibrance", p.vibrance),
                ("u_saturation", p.saturation),
            ):
                program.setUniformValue1f(name, float(value))

            functions.glDrawArrays(0x0005, 0, 4)  # GL_TRIANGLE_STRIP

            self._texture.release(0)
            self._vao.release()
            program.release()
            image = fbo.toImage()
            fbo.release()
            return _qimage_to_rgb(image)
        except Exception as exc:
            self._error = f"renderowanie: {exc}"
            return None
        finally:
            self._context.doneCurrent()


def _qimage_to_rgb(image) -> np.ndarray:
    """QImage -> tablica RGB uint8, jako wlasna kopia danych.

    Kopia jest tu warunkiem poprawnosci, a nie ostroznoscia. `constBits()`
    zwraca widok na pamiec nalezaca do QImage; gdy obiekt ginie przy wyjsciu
    z funkcji, tablica numpy wskazuje na zwolniony obszar. Objawia sie to
    smieciami w obrazie i awaria procesu kilka operacji pozniej - czyli
    daleko od prawdziwej przyczyny.

    `ascontiguousarray` NIE wystarczy: gdy szerokosc jest wielokrotnoscia
    czterech, wyciety fragment jest juz ciagly i funkcja zwraca ten sam widok.
    """
    from PySide6.QtGui import QImage

    converted = image.convertToFormat(QImage.Format_RGB888)
    width, height = converted.width(), converted.height()
    stride = converted.bytesPerLine()  # QImage wyrownuje wiersze do 4 bajtow
    buffer = np.frombuffer(converted.constBits(), dtype=np.uint8, count=height * stride)
    return buffer.reshape(height, stride)[:, : width * 3].reshape(height, width, 3).copy()
