"""Diagnostyka OpenGL krok po kroku.

Naruszenie ochrony pamieci w wiazaniach Qt nie zostawia sladu w Pythonie -
proces po prostu znika. Jedyny sposob, zeby ustalic winowajce, to wypisywac
postep przed kazda operacja i zobaczyc, na ktorej linii urwal sie log.
"""

from __future__ import annotations

import sys

import numpy as np
from PySide6.QtWidgets import QApplication


def step(text: str) -> None:
    print(f"  {text}", flush=True)


app = QApplication(sys.argv)

step("import modułów OpenGL")
from PySide6.QtGui import (  # noqa: E402
    QOffscreenSurface,
    QOpenGLContext,
    QSurfaceFormat,
    QVector2D,
    QVector3D,
)
from PySide6.QtOpenGL import (  # noqa: E402
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)

step("format i powierzchnia")
fmt = QSurfaceFormat()
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.CoreProfile)
surface = QOffscreenSurface()
surface.setFormat(fmt)
surface.create()

step("kontekst")
context = QOpenGLContext()
context.setFormat(fmt)
print(f"    create={context.create()}", flush=True)
print(f"    makeCurrent={context.makeCurrent(surface)}", flush=True)

functions = context.functions()
step("odczyt nazwy karty")
try:
    name = functions.glGetString(0x1F01)
    print(f"    renderer={name!r}", flush=True)
except Exception as exc:
    print(f"    nie udało się: {exc}", flush=True)

VERT = """
#version 330 core
layout(location = 0) in vec2 a_pos;
uniform vec2 u_outSize;
out vec2 v_pixel;
void main() {
    gl_Position = vec4(a_pos, 0.0, 1.0);
    vec2 unit = a_pos * 0.5 + 0.5;
    v_pixel = vec2(unit.x * u_outSize.x, (1.0 - unit.y) * u_outSize.y);
}
"""

FRAG = """
#version 330 core
in vec2 v_pixel;
out vec4 fragColor;
uniform sampler2D u_image;
uniform vec2 u_srcSize;
uniform vec3 u_row0;
uniform vec3 u_row1;
uniform vec3 u_gain;
void main() {
    vec3 p = vec3(v_pixel, 1.0);
    vec2 src = vec2(dot(u_row0, p), dot(u_row1, p));
    vec3 c = texture(u_image, (src + 0.5) / u_srcSize).rgb * u_gain;
    fragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""

step("kompilacja shaderów")
program = QOpenGLShaderProgram()
print(f"    wierzchołki={program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERT)}", flush=True)
print(f"    fragmenty={program.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAG)}", flush=True)
print(f"    link={program.link()}", flush=True)
if program.log():
    print(f"    log: {program.log()}", flush=True)

step("VAO i bufor wierzchołków")
vao = QOpenGLVertexArrayObject()
vao.create()
vao.bind()
vertices = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype=np.float32)
vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
vbo.create()
vbo.bind()
vbo.allocate(vertices.tobytes(), vertices.nbytes)
program.bind()
program.enableAttributeArray(0)
program.setAttributeBuffer(0, 0x1406, 0, 2, 0)
program.release()
vbo.release()
vao.release()

step("tekstura 64x48 float32")
data = np.random.rand(48, 64, 3).astype(np.float32)
texture = QOpenGLTexture(QOpenGLTexture.Target2D)
texture.setFormat(QOpenGLTexture.RGB32F)
texture.setSize(64, 48)
texture.setMinificationFilter(QOpenGLTexture.Linear)
texture.setMagnificationFilter(QOpenGLTexture.Linear)
texture.setWrapMode(QOpenGLTexture.ClampToEdge)
texture.allocateStorage()
texture.setData(QOpenGLTexture.RGB, QOpenGLTexture.Float32, data.tobytes())
print(f"    utworzona={texture.isCreated()}", flush=True)

step("bufor ramki 64x48")
fbo = QOpenGLFramebufferObject(64, 48)
print(f"    poprawny={fbo.isValid()}", flush=True)
fbo.bind()
functions.glViewport(0, 0, 64, 48)

step("program.bind + vao.bind + texture.bind")
program.bind()
vao.bind()
texture.bind(0)

step("uniform sampler (setUniformValue1i)")
program.setUniformValue1i("u_image", 0)

step("uniform vec2 przez QVector2D")
program.setUniformValue("u_outSize", QVector2D(64.0, 48.0))
program.setUniformValue("u_srcSize", QVector2D(64.0, 48.0))

step("uniform vec3 przez QVector3D")
program.setUniformValue("u_row0", QVector3D(1.0, 0.0, 0.0))
program.setUniformValue("u_row1", QVector3D(0.0, 1.0, 0.0))
program.setUniformValue("u_gain", QVector3D(1.0, 1.0, 1.0))

step("glDrawArrays")
functions.glDrawArrays(0x0005, 0, 4)

step("texture.release / vao.release / program.release")
texture.release(0)
vao.release()
program.release()

step("fbo.toImage")
image = fbo.toImage()
print(f"    {image.width()}x{image.height()} format={image.format()}", flush=True)
fbo.release()

step("konwersja QImage -> numpy")
from PySide6.QtGui import QImage  # noqa: E402

converted = image.convertToFormat(QImage.Format_RGB888)
width, height = converted.width(), converted.height()
stride = converted.bytesPerLine()
buffer = converted.constBits()
array = np.frombuffer(buffer, dtype=np.uint8, count=converted.sizeInBytes())
rgb = array.reshape(height, stride)[:, : width * 3].reshape(height, width, 3)
print(f"    numpy {rgb.shape}, średnia {rgb.mean():.1f}", flush=True)

step("porównanie z danymi wejściowymi")
expected = np.clip(data, 0, 1)
expected = np.where(expected <= 0.0031308, expected * 12.92,
                    1.055 * expected ** (1 / 2.4) - 0.055)
# shader nie nakłada krzywej sRGB w tym teście, więc porównujemy surowo
raw_expected = (np.clip(data, 0, 1) * 255 + 0.5).astype(np.uint8)
diff = np.abs(rgb.astype(np.int16) - raw_expected.astype(np.int16))
print(f"    średnia różnica {diff.mean():.2f}, maks {diff.max()}", flush=True)

context.doneCurrent()
print("\nWSZYSTKIE KROKI PRZESZŁY", flush=True)
