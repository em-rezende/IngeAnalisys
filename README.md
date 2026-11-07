# Análisis de Sitio — extensión para IngeTrazo

**Sol · Viento · Clima · Contexto · Masas**, sobre el propio modelo de IngeTrazo.
Es la app web *Análisis de Sitio 3D* convertida en extensión, como un plugin de
SketchUp: no modifica el núcleo; todo entra por `setup(app)` (API de extensiones 2).

## Instalación

1. En IngeTrazo: **Extensiones ▸ Abrir carpeta de extensiones**
   (Windows `%APPDATA%\ingetrazo\plugins\`, Linux/macOS `~/.local/share/ingetrazo/plugins/`).
2. Copia ahí **sólo** la carpeta `analisis_sitio` del ZIP (la carpeta `tests` no hace falta).
   Debe quedar `plugins/analisis_sitio/__init__.py`.
3. Reinicia IngeTrazo. Aparece la pestaña **Análisis de sitio** en la bandeja lateral
   y el submenú **Extensiones ▸ Análisis de sitio**.

Requisitos: IngeTrazo ≥ 0.6 (API 2). Sin dependencias extra (PySide6 + NumPy, ya incluidos).

## La pestaña, en orden

1. **Cargar archivo EPW** — estación, periodo de análisis (meses/horas) y estadísticas.
2. **Ubicación** — búsqueda o «lat, lon», elegir en el mapa, zona horaria. Es el datum del proyecto en IngeTrazo.
3. **Norte del proyecto** — perilla, ángulo, ±15°, o «desde la arista seleccionada». Gira sol, diagrama, mapa y terreno; la geometría no se mueve.
4. **Fecha, hora y sombras** — mueve las sombras reales de IngeTrazo; sol, amanecer/ocaso y clima a esta hora. Subsección *Diagrama solar* (meses, banda, analemas, radio, centro, colores).
5. **Vientos** — rosa de los vientos (gráfico y color), rosa 3D sobre el suelo, flecha del viento horario (azul), flechas animadas (apagadas por defecto), tabla de direcciones y «Aplicar vientos dominantes».
6. **Datos climáticos** — temperatura y humedad relativa mensual del EPW; guardar los gráficos en PNG.
7. **Mapa base y contexto** — mapa base de IngeTrazo y edificios de OpenStreetMap.
8. **Masas y lotes** — desde caras seleccionadas; áreas, pisos, índices de ocupación y construcción.
9. **Anotaciones** — puntos con texto e icono.
10. **Visualización** — mostrar/ocultar el análisis, brújula, anillos, escala de etiquetas, convenciones (leyenda de lo visible) y vistas.
11. **Radiación solar y sombras** — ambos se calculan sobre el modelo y se ven
    en la vista principal, como mapa de color sobre las superficies con su
    **escala gráfica** en un panel flotante arriba a la derecha (debajo del de
    información si ambos están visibles), con su casilla para mostrarlo u ocultarlo.
    Un mapa a la vez; se cambia en «Resultado en la vista».
    - *Superficies*: todo el modelo, masas y lotes, la selección o sólo el suelo;
      con «Suelo alrededor» se añade una malla de suelo (margen automático o fijo),
      recortada bajo los edificios y lotes. Resolución por cara o malla de 2 / 1 / 0.5 m.
    - *Radiación solar incidente*: día de la sección 4, un mes, el periodo de análisis o
      el año. Directa con sombras por trazado de rayos contra todo lo visible (contexto
      OSM incluido) + difusa isótropa con la vista real al cielo (Tregenza) + reflejada
      por el suelo (albedo). EPW, o cielo despejado teórico sin EPW. Paletas Ecotect,
      grises o térmica; escala automática o fija. kWh/m².
    - *Estudio de sombras*: el día de la sección 4, de una hora a otra, cada 15, 20, 30 o
      60 minutos; cada punto acumula las horas en sombra (sombra arrojada y propia).
      Se muestra como **horas de sombra** u **horas de sol (asoleamiento)**, en grises
      (blanco = sol, negro = sombra) o en **colores por horas estilo Ecotect** (una clase
      por hora, de amarillo = sol a azul marino = sombra, con su leyenda por clases).
      Al pasar de sombra a sol cada punto conserva su color; cambian los rótulos.
      En sombras, las paletas Ecotect y Térmica se leen al revés que en radiación:
      amarillo / blanco = lo más iluminado, azul / negro = lo más sombreado.
    - Los mapas son grupos bloqueados en la capa «Radiación solar»: se guardan en el
      .igz, se quitan y se deshacen en un paso. No se generan informes PDF.
12. **Exportar imagen** — PNG de la vista (hasta 5K), con el mapa y su escala si están
    visibles. Al final, la casilla **Mostrar panel flotante de información y
    convenciones** (título y posición configurables). Está oculto al iniciar
    IngeTrazo; si se muestra, también sale en la imagen.

La rueda del ratón desplaza la pestaña: los desplegables y casillas numéricas sólo
cambian con la rueda después de hacer clic en ellos.

Clic derecho sobre una cara: *Convertir en masa / lote*; sobre una masa: *Editar masa*.
Todo cambio de geometría o contenido es **un paso de deshacer**.

## Diferencias con la app web

- La importación de OBJ/DXF, el modelado y la exportación OBJ los hace IngeTrazo.
- El tono del mapa (gris/oscuro) y el recoloreado de zonas verdes no aplican: el mapa
  es la capa base de IngeTrazo (sí tiene opacidad).
- La librería de iconos usa símbolos Unicode; si el sistema no tiene fuente de emoji
  se dibuja un punto de color.
- Las anotaciones se dibujan siempre de pie (sin la opción «sobre el suelo»).

## Datos en el documento

`plugin_data["analisis_sitio"]` (anotaciones, vientos — con deshacer),
`analisis_sitio.vista` (ajustes de visualización), `analisis_sitio.clima` (EPW compacto),
`analisis_sitio.contexto` (edificios OSM). Masas: `group.ext["analisis_sitio"]`.

## Estructura

```
analisis_sitio/
  __init__.py     setup(app): panel, overlay, selección, menús, navegador
  nucleo.py       controlador: sitio, hora (= sombras), clima, animación
  datos.py        valores en el documento y el comando de deshacer
  clima.py        EPW, estadísticas, rosa, paletas OKLab
  solar.py        trayectorias, analemas, banda, salida/puesta
  osm.py          Overpass en segundo plano
  geometria.py    prismas, masas, contexto
  acciones.py     operaciones sin interfaz (las usan panel, menús y pruebas)
  dibujo.py       todo lo que se pinta sobre la vista
  graficos.py     rosa de vientos y clima mensual
  panel.py        la pestaña lateral
  herramientas.py herramienta de un clic con inferencias
  exportar.py     imagen PNG y gráficos del clima
  radiacion.py    radiación incidente y horas de sombra (trazado de rayos)
```

Pruebas: `tests/test_analisis_sitio.py` (copiar a `tests/` del repositorio y poner la
carpeta `analisis_sitio` en la raíz o en `plugins/`), `python -m pytest tests/test_analisis_sitio.py`.

Licencia: GPL‑3.0‑or‑later, como IngeTrazo. Datos de edificios © colaboradores de OpenStreetMap.
