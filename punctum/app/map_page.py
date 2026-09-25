"""Strona mapy: Leaflet w silniku przegladarki.

Kod przeniesiony z osobnej aplikacji GeoTagger (D:\\...\\geotagger_py), napisanej
w PyQt6. Dwa wiazania Qt nie moga wspolistniec w jednym procesie - kazde laduje
wlasna kopie bibliotek Qt - wiec strona zostala przeniesiona, a nie uruchomiona
obok. Sama tresc strony jest w czystym HTML-u i JavaScripcie, wiec przeniosla
sie bez zmian; zmienil sie tylko sposob rozmowy z Pythonem.

Most: **QWebChannel**, a nie odpytywanie kolejki. Stara aplikacja importowala
QWebChannel, ale go nie uzywala - wstrzykiwala kolejke komunikatow i opozniala
ja zegarem co 100 ms. Klikniecie w mape potrafilo przez to odpowiedziec z
poltorej dziesiatej sekundy opoznienia, a zegar mielil w kolko przez caly czas
zycia okna. QWebChannel wola Pythona wprost, w momencie zdarzenia.

Mapa wymaga sieci: kafelki i biblioteka Leaflet ida z internetu. Bez polaczenia
zostaje szare tlo - widok mowi o tym wprost, zamiast udawac, ze sie laduje.
"""

from __future__ import annotations

import html

from ..przeklad import N_, t

MAP_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
html,body,#map { width:100%; height:100%; background:#141418; }
.search-bar {
  position:absolute; top:10px; left:50%; transform:translateX(-50%);
  z-index:1000; display:flex; gap:6px; min-width:340px;
}
#searchBox {
  flex:1; padding:8px 12px; background:rgba(28,28,34,0.95);
  border:1px solid rgba(255,255,255,0.15); border-radius:6px;
  color:#e8e8ea; font-size:13px; outline:none;
  font-family:'Segoe UI',sans-serif;
}
#searchBox:focus { border-color:#6c63ff; }
#searchBtn {
  padding:8px 14px; background:#6c63ff; border:none; border-radius:6px;
  color:white; font-size:13px; cursor:pointer; font-family:'Segoe UI',sans-serif;
}
#searchBtn:hover { background:#7a72ff; }
#results {
  position:absolute; top:calc(100% + 4px); left:0; right:0;
  background:rgba(28,28,34,0.98); border:1px solid rgba(255,255,255,0.15);
  border-radius:6px; overflow:hidden; display:none; max-height:220px; overflow-y:auto;
}
#results.show { display:block; }
.ri {
  padding:8px 12px; cursor:pointer; border-bottom:1px solid rgba(255,255,255,0.06);
  font-family:'Segoe UI',sans-serif;
}
.ri:hover { background:rgba(108,99,255,0.2); }
.ri .rn { font-size:12px; font-weight:600; color:#e8e8ea; }
.ri .rd { font-size:10px; color:#8a8a90; margin-top:1px; }
.layer-sw {
  position:absolute; bottom:34px; right:10px; z-index:1000;
  display:flex; flex-direction:column; gap:4px;
}
.lb {
  display:flex; align-items:center; gap:6px; padding:5px 10px;
  background:rgba(28,28,34,0.95); border:1px solid rgba(255,255,255,0.12);
  border-radius:6px; color:#8a8a90; font-size:11px; cursor:pointer;
  font-family:'Segoe UI',sans-serif; white-space:nowrap; transition:all .15s;
}
.lb:hover, .lb.on { border-color:#6c63ff; color:#b9b3ff; background:rgba(108,99,255,0.15); }
.lsw { width:20px; height:14px; border-radius:3px; border:1px solid rgba(255,255,255,0.1); }
.ls-osm { background:linear-gradient(135deg,#3a5a2a,#8aa870); }
.ls-dk { background:linear-gradient(135deg,#1a1a2e,#2d2d44); }
.ls-sa { background:linear-gradient(135deg,#1a3050,#2a5040); }
.ls-hy { background:linear-gradient(135deg,#1a3050,#3a4020); }
.coords-bar {
  position:absolute; bottom:0; left:0; right:0; z-index:1000;
  background:rgba(20,20,24,0.9); border-top:1px solid rgba(255,255,255,0.07);
  padding:4px 12px; font-size:10px; color:#8a8a90; font-family:'Consolas',monospace;
  display:flex; align-items:center; gap:16px;
}
.mode-pill {
  display:inline-flex; align-items:center; gap:5px;
  padding:2px 8px; border-radius:20px; background:rgba(255,255,255,0.06);
  font-family:'Segoe UI',sans-serif; font-size:10px;
}
.mode-pill .dot { width:6px; height:6px; border-radius:50%; background:#8a8a90; }
.mode-pill.on { background:rgba(108,99,255,0.25); color:#b9b3ff; }
.mode-pill.on .dot { background:#6c63ff; }
.ppop { font-family:'Segoe UI',sans-serif; text-align:center; }
.ppop img { max-width:150px; border-radius:4px; display:block; margin:0 auto 4px; }
.ppop .pn { font-size:12px; font-weight:600; }
.ppop .pc { font-size:10px; color:#666; font-family:'Consolas',monospace; }
#offline {
  position:absolute; inset:0; z-index:2000; display:none;
  align-items:center; justify-content:center; text-align:center;
  background:#141418; color:#8a8a90; font-family:'Segoe UI',sans-serif;
  font-size:13px; padding:40px; line-height:1.6;
}
#offline.show { display:flex; }
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
<div class="search-bar">
  <div style="position:relative;flex:1">
    <input id="searchBox" placeholder="Wyszukaj miasto, ulicę, miejsce…"
           onkeydown="if(event.key==='Enter')doSearch()">
    <div id="results"></div>
  </div>
  <button id="searchBtn" onclick="doSearch()">Szukaj</button>
</div>
<div id="map"></div>
<div class="layer-sw">
  <div class="lb on" id="lOsm" onclick="swL('osm')"><div class="lsw ls-osm"></div>Mapa</div>
  <div class="lb" id="lDark" onclick="swL('dark')"><div class="lsw ls-dk"></div>Ciemna</div>
  <div class="lb" id="lSat" onclick="swL('sat')"><div class="lsw ls-sa"></div>Satelita</div>
  <div class="lb" id="lHybrid" onclick="swL('hybrid')"><div class="lsw ls-hy"></div>Hybryda</div>
</div>
<div class="coords-bar">
  <div class="mode-pill" id="mpill"><span class="dot"></span><span id="modeText">Przeglądanie</span></div>
  <span id="coordsText"></span>
</div>
<div id="offline">Mapa potrzebuje połączenia z internetem —<br>kafelki i biblioteka mapy pobierane są z sieci.</div>

<script>
// Bez Leafletu nie ma czego rysowac. Zamiast pustego, szarego prostokata
// mowimy wprost, czego brakuje.
const hasMap = (typeof L !== 'undefined');
if (!hasMap) {
  document.getElementById('offline').classList.add('show');
} else {

const map = L.map('map', {zoomControl:true}).setView([52.069, 19.480], 6);
const TL = {
  osm:    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            {attribution:'&copy; OpenStreetMap', maxZoom:19}),
  dark:   L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
            {attribution:'&copy; Stadia', maxZoom:20}),
  sat:    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {attribution:'&copy; Esri', maxZoom:20}),
  hybrid: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {attribution:'&copy; Esri', maxZoom:20}),
};
const hybridLabels = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {attribution:'&copy; OSM', maxZoom:19, opacity:0.35});
let current = 'osm';
TL.osm.addTo(map);

const markers = {};
let tagging = false;
let found = [];
let foundMarker = null;

function icon(color, size, glow) {
  return L.divIcon({className:'', iconSize:[size,size], iconAnchor:[size/2,size],
    popupAnchor:[0,-(size+4)],
    html:`<div style="width:${size}px;height:${size}px;background:${color};
      border:2px solid rgba(255,255,255,0.85);border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);box-shadow:0 2px 8px ${glow}"></div>`});
}
const pinPlain    = icon('#6c63ff', 22, 'rgba(108,99,255,0.6)');
const pinSelected = icon('#b9b3ff', 26, 'rgba(185,179,255,0.8)');
const pinFound    = icon('#ffd166', 24, 'rgba(255,209,102,0.8)');

function swL(name) {
  if (name === current) return;
  map.removeLayer(TL[current]);
  if (current === 'hybrid') map.removeLayer(hybridLabels);
  TL[name].addTo(map);
  if (name === 'hybrid') hybridLabels.addTo(map);
  current = name;
  ['osm','dark','sat','hybrid'].forEach(key => {
    const box = document.getElementById('l' + key.charAt(0).toUpperCase() + key.slice(1));
    if (box) box.classList.toggle('on', key === name);
  });
}
window.swL = swL;

map.on('mousemove', event => {
  document.getElementById('coordsText').textContent =
    event.latlng.lat.toFixed(5) + ', ' + event.latlng.lng.toFixed(5);
});

map.on('click', event => {
  if (tagging && window.bridge) window.bridge.mapClicked(event.latlng.lat, event.latlng.lng);
});

function setTagging(on) {
  tagging = on;
  const pill = document.getElementById('mpill');
  const text = document.getElementById('modeText');
  pill.className = on ? 'mode-pill on' : 'mode-pill';
  text.textContent = on ? 'Kliknij mapę, aby przypisać' : 'Przeglądanie';
  map.getContainer().style.cursor = on ? 'crosshair' : '';
}
window.setTagging = setTagging;

function addMarker(path, lat, lon, name) {
  if (markers[path]) map.removeLayer(markers[path]);
  const marker = L.marker([lat, lon], {icon: pinPlain}).addTo(map);
  marker.bindPopup(`<div class="ppop"><div class="pn">${name}</div>
    <div class="pc">${lat.toFixed(5)}, ${lon.toFixed(5)}</div></div>`);
  marker.on('click', () => { if (window.bridge) window.bridge.markerClicked(path); });
  markers[path] = marker;
}
window.addMarker = addMarker;

function clearMarkers() {
  Object.values(markers).forEach(m => map.removeLayer(m));
  Object.keys(markers).forEach(k => delete markers[k]);
}
window.clearMarkers = clearMarkers;

function highlight(paths) {
  Object.entries(markers).forEach(([path, marker]) => {
    marker.setIcon(paths.includes(path) ? pinSelected : pinPlain);
  });
}
window.highlight = highlight;

function fitToMarkers() {
  const points = Object.values(markers).map(m => m.getLatLng());
  if (!points.length) return;
  if (points.length === 1) { map.setView(points[0], 15); return; }
  // maxZoom jest tu istotne: kilkanascie zdjec z tego samego miejsca daje
  // ramke o zerowym rozmiarze i mapa skakalaby na maksymalne powiekszenie,
  // czyli na kilka metrow - widok bez zadnego kontekstu.
  map.fitBounds(L.latLngBounds(points), {padding:[40,40], maxZoom:16});
}
window.fitToMarkers = fitToMarkers;

function panTo(lat, lon, zoom) { map.setView([lat, lon], zoom || 14); }
window.panTo = panTo;

// Do testow i diagnostyki. Zrzut ekranu widoku sieciowego wychodzi bialy -
// Qt rysuje go osobna warstwa - wiec zamiast ogladac piksele pytamy strone,
// co u niej slychac: ile kafelkow sie wczytalo i ile jest pinezek.
window.mapState = function() {
  return JSON.stringify({
    tiles: document.querySelectorAll('img.leaflet-tile-loaded, img.leaflet-tile').length,
    markers: Object.keys(markers).length,
    tagging: tagging,
    layer: current,
    center: [map.getCenter().lat, map.getCenter().lng],
    zoom: map.getZoom()
  });
};

async function doSearch() {
  const query = document.getElementById('searchBox').value.trim();
  if (!query) return;
  const box = document.getElementById('results');
  box.innerHTML = '<div class="ri"><div class="rn">Szukanie…</div></div>';
  box.classList.add('show');
  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}` +
      `&format=json&limit=7&accept-language=pl`);
    found = await response.json();
    if (!found.length) {
      box.innerHTML = '<div class="ri"><div class="rn" style="color:#8a8a90">Brak wyników</div></div>';
      return;
    }
    box.innerHTML = found.map((item, index) => `
      <div class="ri" onclick="pickResult(${index})">
        <div class="rn">${item.display_name.split(',')[0]}</div>
        <div class="rd">${item.display_name.split(',').slice(1,4).join(',')}</div>
      </div>`).join('');
  } catch (error) {
    box.innerHTML = '<div class="ri"><div class="rn" style="color:#ff6b6b">Błąd połączenia</div></div>';
  }
}
window.doSearch = doSearch;

function pickResult(index) {
  const item = found[index];
  if (!item) return;
  const lat = parseFloat(item.lat), lon = parseFloat(item.lon);
  document.getElementById('results').classList.remove('show');
  document.getElementById('searchBox').value = item.display_name.split(',').slice(0,2).join(',');
  map.setView([lat, lon], 14);
  if (foundMarker) map.removeLayer(foundMarker);
  foundMarker = L.marker([lat, lon], {icon: pinFound}).addTo(map);
  foundMarker.bindPopup(`<div class="ppop"><div class="pn">${item.display_name.split(',')[0]}</div>
    <div class="pc">${lat.toFixed(5)}, ${lon.toFixed(5)}</div></div>`).openPopup();
  if (window.bridge) window.bridge.placeFound(lat, lon, item.display_name.split(',')[0]);
}
window.pickResult = pickResult;

document.addEventListener('click', event => {
  if (!event.target.closest('.search-bar')) {
    document.getElementById('results').classList.remove('show');
  }
});

}

// Most do Pythona. Wolamy wprost w chwili zdarzenia - bez kolejki i bez zegara.
// Zglaszamy sie ZAWSZE, takze gdy mapy nie ma: inaczej program czekalby w
// nieskonczonosc na strone, ktora nigdy nie odpowie, i nie wiedzialby dlaczego.
new QWebChannel(qt.webChannelTransport, function(channel) {
  window.bridge = channel.objects.bridge;
  window.bridge.ready(hasMap);
});
</script>
</body>
</html>
"""

# Napisy strony w kolejnosci od najdluzszych, zeby krotszy nie wszedl w srodek
# dluzszego. Strona nie pyta Pythona o teksty - podmieniamy je w HTML-u przed
# wczytaniem, bo jezyk i tak zmienia sie dopiero po ponownym starcie.
NAPISY = (
    N_("kafelki i biblioteka mapy pobierane są z sieci."),
    N_("Mapa potrzebuje połączenia z internetem —"),
    N_("Wyszukaj miasto, ulicę, miejsce…"),
    N_("Kliknij mapę, aby przypisać"),
    N_("Błąd połączenia"),
    N_("Przeglądanie"),
    N_("Brak wyników"),
    N_("Szukaj"),
)


# Nazwy warstw podmieniane razem z otaczajacymi znacznikami - samo "Mapa"
# trafiloby tez w srodek innych zdan.
WARSTWY = (N_("Mapa"), N_("Ciemna"), N_("Satelita"), N_("Hybryda"))


def strona() -> str:
    """HTML mapy z napisami w biezacym jezyku."""
    tekst = MAP_HTML
    for warstwa in WARSTWY:
        tekst = tekst.replace(f"</div>{warstwa}</div>", f"</div>{html.escape(t(warstwa))}</div>")
    for napis in NAPISY:
        # Apostrof zamieniony na typograficzny: czesc napisow stoi w JS
        # w pojedynczych cudzyslowach i zwykly apostrof zamknalby napis.
        tekst = tekst.replace(napis, html.escape(t(napis), quote=False).replace("'", "’"))
    return tekst
