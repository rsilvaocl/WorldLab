# Design — WorldLab

<!-- impeccable:design -->

Registrado desde el mundo construido en `viewer.html`, no desde la intención.
La superficie es una sola: el **Panel de corrida**. Modo **Operate** con lectura
doble (investigador + revisor externo).

## Mundo visual

**Panel de instrumentos de vuelo nocturno.** Un agente de WorldLab vuela a
ciegas: no hay referencia exterior, solo lo que dicen sus instrumentos. El
revisor hace lo que hace un piloto en IMC — el cross-check: instrumentos que
deben concordar. Elegido por el usuario sobre el candidato asignado por el
sorteo (clave `e56a24a1`); fuente del retador:
`signals-instruments-night-flight-six-pack`.

Lo que este mundo **rechaza**: el arreglo por defecto de la categoría — lienzo
oscuro, grilla, acento neón, panel lateral y scrubber. La diferencia no es de
paleta: la integridad de la corrida es el primer readout, antes que la
animación.

## Tokens

### Superficie
| token | valor | uso |
|---|---|---|
| `--panel` | `#0b0d0f` | negro mate del panel, con textura fina |
| `--panel-hi` | `#12151a` | rieles superior e inferior |
| `--face` | `#111417` | cara de instrumento, hundida tras vidrio |
| `--face-deep` | `#080a0c` | cara del instrumento principal (el mundo) |
| `--bezel` / `--bezel-hi` | `#1c2126` / `#2b3238` | bisel y su reflejo |

### Marcas
| token | valor | contraste sobre `--panel` |
|---|---|---|
| `--lum` | `#f2f5f2` | 16.8:1 |
| `--lum-2` | `#a7b0ae` | 7.6:1 |
| `--lum-3` | `#7d8785` | 4.6:1 — piso para placas |

### Lámparas — el color significa una sola cosa
| token | valor | significado |
|---|---|---|
| `--green` | `#39ff9a` | **medido**: viene del motor |
| `--amber` | `#ffb000` | **derivado o atención**: lo infiere el visor, o hay algo oculto |
| `--red` / `--red-txt` | `#ff3b30` / `#ff7a70` | **fallo o barrera cerrada** |

`--red` es solo gráfico (lámparas, muro, aspas). Para texto se usa `--red-txt`.

### Canales de tripulación
`#39ff9a · #ffb000 · #5ac8fa · #ff6fd8 · #c4f24a` — tintas de pluma, una por
agente, estables entre panel y mapa.

### Regiones
`--reg-a #5ac8fa` (oeste) · `--reg-b #c08cff` (este). Nunca solas: llevan
rótulo impreso en la cara, muro divisorio y trama de barrera.

## Tipografía

**Saira Condensed**, subseteada a latín + acentos y **embebida en base64**
(~24 KB, tres pesos). No es un fallback del sistema: el visor debe abrir desde
`file://` sin red, y la letra de placa condensada es parte del mundo.

| rol | tamaño | tratamiento |
|---|---|---|
| readout grande | 30px / 700 | `tabular-nums`, tracking −.02em |
| título de corrida | 16px / 700 | versalitas, tracking .22em |
| valor de instrumento | 17–21px / 700 | `tabular-nums` |
| cuerpo | 15px / 400 | |
| placa (`.placard`, `h2`) | 11px / 600 | versalitas, tracking .16em |
| clave de placa | 9.5px / 600 | versalitas, tracking .15em |

Escala con pasos reales (≈1.3), no catorce tamaños entre 10 y 19px.
Monoespaciada (`ui-monospace`) **solo** para `raw_response` — es código, no
disfraz técnico.

## Componentes

- **`.inst`** — bisel con cuatro tornillos de esquina (`::before`, `::after`,
  `.scr.bl`, `.scr.br`) y cara hundida con una sola banda de reflejo
  antirreflejo. Radio 3px: el panel es escuadrado.
- **`.nameplate`** — placa grabada bajo el instrumento.
- **`.lamp`** — anunciador. Apagado = gris; encendido = color + bulbo con halo.
  Con `data-go` es un botón que lleva a su instrumento.
- **`.sw`** — interruptor de panel, 44px de alto mínimo. `aria-pressed` lo
  enciende en verde relleno.
- **`.tape`** — cinta vertical de energía con línea roja al 20%. Anima
  `transform: scaleY`, nunca `height`.
- **`.calScale`** — la escala de 6 niveles del probe. **Aguja blanca = lo que
  el agente predijo. Índice ámbar = la verdad del motor.** La distancia es el
  resultado.
- **`.quad`** — el cuadrante 2×2 (región × fase). La celda retenida va rayada
  en rojo con `?`.

## Movimiento

Un solo momento autorado: la aguja amortiguada.
`--damp: cubic-bezier(.16,1,.3,1)` — salida exponencial, **sin rebote**: un
instrumento amortiguado es precisamente el que no oscila. Se aplica a la aguja
de calibración y a las cintas de energía. Nada más se mueve.

Reproducción por `requestAnimationFrame` con acumulador (260 ms por momento a
1×), no `setInterval`. `prefers-reduced-motion` anula todo.

## Reglas duras

1. **El color nunca es el único portador.** Los cuatro símbolos del mundo se
   dibujan como **formas distintas** (círculo, triángulo, cuadrado, rombo,
   hexágono, triángulo invertido) además de su color. Región, fase, éxito y
   fallo llevan forma, rótulo o palabra.
2. **Verde = medido, ámbar = derivado.** Fase inferida, barrera supuesta,
   alias de recursos y filtros activos se declaran en ámbar. El visor nunca
   presenta una inferencia como una observación.
3. **Los fallos se ven por defecto.** `okOnly` arranca en `false`. Filtrar
   enciende una lámpara ámbar y el contador dice cuántas se ocultan.
4. **Cero red.** Fuentes embebidas, iconos SVG autorados, sin emoji ni glifos
   Unicode haciendo de sistema de iconos.
5. **El fondo estático se cachea** por fase en un canvas fuera de pantalla; por
   fotograma solo se dibujan entidades.
6. **`[hidden]{display:none !important}`** — una regla `display` de autor le
   gana al atributo `hidden` del UA.

## Adaptación

- **≥1180px** — dos columnas: mundo `1fr` + instrumentos `372px`.
- **900–1180px** — misma estructura, columna a `320px`.
- **≤900px** — se apila; la altura la manda el contenido (`html,body{height:auto}`,
  deck y port a `flex:none`) y la cara del mundo toma la proporción real del
  mundo por JS. Sin esto la cara colapsa o el transporte se le encima.
- **≤560px** — riel compacto, velocidad a ancho completo, placa de corrida 2×2.

El tamaño de celda se calcula del espacio disponible (`layout()`), nunca fijo:
un mundo de 60×60 y uno de 15×15 caben igual.
