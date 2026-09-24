# Ideas y roadmap futuro

> Idioma: español. [Read this roadmap in English](roadmap.en.md).

Este documento registra posibilidades de mejora. Nada de esta lista debe
interpretarse como funcionalidad disponible. Cada cambio que amplíe la
envolvente de compatibilidad deberá mantener el principio *fail-closed*, incluir
pruebas automatizadas y pasar primero por revisión estática de G-code.

## Índice

- [Prioridad sugerida](#prioridad-sugerida)
  - [Próximas mejoras de diagnóstico](#próximas-mejoras-de-diagnóstico)
  - [Políticas de orden de impresión](#políticas-de-orden-de-impresión)
  - [Detección de colisiones](#detección-de-colisiones)
- [Mejoras de seguridad y compatibilidad](#mejoras-de-seguridad-y-compatibilidad)
  - [Parser modal explícito](#parser-modal-explícito)
  - [Validación más completa del perfil](#validación-más-completa-del-perfil)
  - [Impresión secuencial por múltiples etapas](#impresión-secuencial-por-múltiples-etapas)
  - [Detección automática de etapas térmicas](#detección-automática-de-etapas-térmicas)
  - [Pausa opcional para cambio de filamento](#pausa-opcional-para-cambio-de-filamento-entre-etapas)
  - [Transiciones y estacionamiento](#transiciones-configurables-y-zona-de-estacionamiento)
  - [Control térmico ampliado](#control-térmico-ampliado)
- [Calidad y pruebas](#calidad-y-pruebas)
- [Experiencia de uso](#experiencia-de-uso)
- [Ideas provenientes de pruebas físicas](#registro-de-ideas-provenientes-de-pruebas-físicas)

## Tabla resumen

| Área | Propuestas principales | Prioridad sugerida | Estado general |
|---|---|---|---|
| Diagnóstico y auditoría | Log de última ejecución, validador CLI y resumen incrustado | Alta | Pendiente |
| Orden de impresión | Orden por altura, posición, distancia o selección manual | Media | Pendiente |
| Seguridad física | Detección de colisiones y zona segura de estacionamiento | Alta | Investigación necesaria |
| Compatibilidad G-code | Parser modal y validación ampliada del perfil | Alta | Pendiente |
| Impresión por etapas | Múltiples fronteras configurables y detección térmica automática | Media | Diseño propuesto |
| Cambio de filamento | Pausa, beep, estacionamiento y reanudación segura | Media | Diseño propuesto |
| Control térmico | Más comandos, herramientas y modo conservador | Media | Parcialmente implementado |
| Calidad | Fixtures reales, fuzzing, comparador semántico y matriz de compatibilidad | Alta | En progreso |
| Experiencia de uso | Validación, mensajes, vista previa y checklist | Media | Pendiente |

## Prioridad sugerida

### Próximas mejoras de diagnóstico

#### Informe de la última ejecución

Generar un archivo de auditoría que se sobrescriba en cada ejecución, sin
histórico acumulativo. Debería registrar como mínimo:

- versión del script y de Cura;
- perfil y parámetros relevantes;
- cantidad de bloques, objetos y capas detectados;
- modos XYZ/E encontrados y sus transiciones;
- alturas máximas, clearance y puntos XYZ de reanudación;
- preámbulos interobjeto detectados;
- esperas térmicas conservadas u omitidas y el motivo;
- orden original y orden resultante;
- resultado `APPLIED` o `REJECTED`, con la validación que decidió el rechazo;
- hash del G-code de entrada y salida para identificar exactamente lo auditado.

El log no debería incluir el G-code completo ni rutas innecesarias. Antes de
implementarlo hay que confirmar una ubicación escribible y estable dentro de la
configuración de Cura. Como alternativa más portable, se podría generar un
informe breve dentro de comentarios del propio G-code y ofrecer un log externo
solo como opción.

**Criterio de aceptación:** una ejecución nueva reemplaza atómicamente el informe
anterior; un fallo al escribir el log no debe producir un G-code parcialmente
transformado ni ocultar el resultado real.

#### Validador independiente de línea de comandos

Crear una pequeña herramienta que reciba el G-code original y el transformado,
sin necesitar Cura, y produzca un informe de auditoría. Podría comprobar orden de
capas, conservación de trayectorias, estados modales, temperaturas, límites XYZ
y contenido añadido/eliminado.

**Valor:** facilita revisar archivos reales, automatizar regresiones y adjuntar
un informe reproducible a incidencias.

#### Resumen de auditoría incrustado

Agregar al encabezado comentarios legibles como número de objetos, política de
orden, transiciones calculadas, esperas térmicas omitidas y versión del
transformador. Esto ayuda incluso cuando el archivo de log externo no está
disponible.

### Políticas de orden de impresión

Permitir escoger cómo completar los objetos después de las capas comunes:

- orden original de Cura;
- menor a mayor altura;
- mayor a menor altura;
- izquierda a derecha o derecha a izquierda;
- adelante hacia atrás o atrás hacia adelante;
- distancia mínima desde una posición de inicio;
- orden manual definido por el usuario.

Para hacerlo correctamente será necesario identificar cada objeto sin depender
solo de `;MESH:`, calcular una caja envolvente confiable y mover junto con el
objeto todos sus preámbulos y estados asociados.

**Criterio de aceptación:** la política debe ser determinista, mostrarse en la
auditoría y preservar exactamente todas las trayectorias pertenecientes a cada
objeto. Si dos objetos no pueden identificarse inequívocamente, se conserva el
orden original o se rechaza la transformación.

### Detección de colisiones

Investigar una verificación geométrica del cabezal, carro y eje X contra piezas
ya terminadas. Posibles enfoques:

1. **Integración con la geometría de Cura antes de exportar.** Usar modelos de
   volumen de exclusión del cabezal y las posiciones originales de los objetos.
2. **Validador externo.** Simular la trayectoria del volumen completo del carro,
   no solo de la boquilla, contra mallas o cajas envolventes de las piezas.
3. **Integración con un simulador existente.** Exportar el G-code y la geometría
   de máquina a una herramienta que pueda reportar intersecciones.
4. **Aproximación conservadora por volúmenes.** Usar cajas/cilindros de exclusión
   sobredimensionados cuando no exista una malla exacta del cabezal.

Un posprocesador que solo recibe G-code no siempre dispone de las mallas ni de la
geometría completa del carro. Es probable que una solución fuerte necesite un
plugin de Cura previo al G-code o una segunda herramienta externa.

**Criterio de aceptación:** comprobar todos los movimientos posteriores a la
terminación de cada objeto, incluir tolerancias configurables y rechazar ante
geometría ausente o ambigua. Una comprobación positiva reduce riesgo, pero no
debe presentarse como garantía absoluta de seguridad física.

## Mejoras de seguridad y compatibilidad

### Parser modal explícito

Reemplazar gradualmente búsquedas independientes por un intérprete reducido de
estado G-code: `G90/G91`, `M82/M83`, XYZ/E, herramienta activa, temperaturas,
ventilador, aceleración y unidades. El parser admitiría únicamente comandos y
formatos documentados; cualquier construcción desconocida relevante produciría
rechazo.

### Validación más completa del perfil

- confirmar una sola extrusora y ausencia de cambios `Tn`;
- comprobar límites X/Y además de altura Z;
- validar sabor Marlin desde perfil y encabezado;
- registrar dimensiones y geometría declarada del cabezal;
- detectar prime tower, ooze shield, draft shield y estructuras compartidas;
- comprobar que los ajustes efectivos coincidan con los codificados en el
  comentario `SETTING_3` cuando esté disponible.

### Impresión secuencial por múltiples etapas

Permitir configurar varias capas en las que comienza una nueva etapa. Por
ejemplo, con dos objetos `A` y `B` y transiciones en las capas impresas 3, 8 y
16, el orden sería:

```text
A1..2, B1..2,
A3..7, B3..7,
A8..15, B8..15,
A16..fin, B16..fin
```

La interfaz debería usar numeración humana desde 1 y convertirla internamente a
la numeración de Cura, que comienza en `;LAYER:0`. También deberá normalizar la
lista, rechazar números repetidos o fuera de rango y explicar claramente los
tramos resultantes antes de transformar el archivo.

Cada cambio de objeto entre tramos requiere una transición segura, restauración
del estado modal y validación de las capas disponibles. La comprobación de
colisiones deberá considerar la altura que ya alcanzó cada objeto, no solo las
piezas completamente terminadas.

**Criterio de aceptación:** cada trayectoria original aparece exactamente una
vez, los límites de cada etapa corresponden a las capas solicitadas y el orden
resultante queda registrado en la auditoría. Una configuración ambigua o
incompatible debe rechazarse sin modificar el G-code.

### Detección automática de etapas térmicas

Analizar los objetivos de temperatura de cama y extrusor para proponer las
capas donde debería comenzar una nueva etapa. Por ejemplo, si las capas impresas
1 y 2 usan 230 °C y desde la capa 3 se solicitan 225 °C, el script propondría la
capa 3 como frontera y, con dos objetos, produciría conceptualmente:

```text
A1..2, B1..2, A3..fin, B3..fin
```

La detección no debe interpretar mecánicamente la ubicación de un `M104` o
`M140`: Cura puede emitir un cambio al final de la capa anterior para anticipar
el calentamiento o enfriamiento. Será necesario inferir a qué capa está
destinado el nuevo objetivo y distinguir una transición real de una orden
anticipada, una espera, una oscilación o un ajuste incidental.

El análisis debería:

- tratar por separado la cama y cada extrusor compatible;
- comparar el patrón térmico de todos los objetos;
- exigir fronteras equivalentes y objetivos coherentes entre ellos;
- admitir la detección de varias fronteras térmicas;
- mostrar las capas propuestas antes de transformar;
- permitir aceptar, modificar o ignorar la propuesta;
- registrar qué comandos y capas originaron cada decisión.

Si los objetos presentan patrones diferentes, comandos ambiguos u oscilaciones
que no puedan atribuirse con seguridad a una capa, el modo automático debe
rechazar la propuesta sin modificar el G-code. El usuario aún podría configurar
manualmente las etapas mediante la función anterior.

**Criterio de aceptación:** para cada frontera propuesta, el informe identifica
la temperatura anterior, la nueva temperatura, la capa impresa a la que se
atribuye el cambio y la evidencia equivalente en todos los objetos. La salida no
se transforma hasta que la selección quede confirmada explícitamente.

### Pausa opcional para cambio de filamento entre etapas

Permitir insertar una pausa con aviso sonoro entre dos etapas, especialmente
entre la etapa común inicial y la terminación secuencial de los objetos. La
secuencia podría incluir:

- retracción controlada;
- elevación y estacionamiento en una zona segura validada;
- aviso sonoro mediante `M300`, cuando el firmware lo admita;
- pausa mediante el comando compatible con el firmware, por ejemplo `M0` o
  `M25`;
- restauración de temperatura, posición, modo XYZ, modo de extrusión y cantidad
  retraída antes de reanudar.

La pausa debe ser opcional por frontera de etapa, de modo que también pueda
utilizarse con múltiples alturas para imprimir varios cambios de color. Su
implementación dependerá del firmware y del método de impresión utilizado
(tarjeta SD, USB u OctoPrint), porque los comandos de pausa no se comportan igual
en todos los entornos.

**Criterio de aceptación:** la máquina queda estacionada sin cruzar piezas, el
cambio de filamento no altera las coordenadas ni la extrusión posterior y el
archivo identifica explícitamente el comando de pausa elegido y su
compatibilidad esperada.

### Transiciones configurables y zona de estacionamiento

Permitir una posición de espera/purga validada fuera de las piezas para los casos
en que una espera térmica sea realmente necesaria. Podría incluir retracción,
estacionamiento, recuperación y una trayectoria de limpieza, pero solo con una
zona libre demostrable y límites de máquina verificados.

### Control térmico ampliado

- reconocer de forma segura parámetros `R`, herramientas `Tn` y varias
  extrusoras;
- explicar en la auditoría por qué cada espera se mantuvo o eliminó;
- ofrecer un modo conservador que nunca elimine esperas;
- comprobar mediante pruebas que los objetivos activos no cambien al reordenar.

## Calidad y pruebas

### Fixtures reales anonimizados

Mantener pequeños G-code reales de versiones compatibles de Cura, reducidos y
sin información privada, junto con el resultado esperado. Los archivos grandes
pueden representarse mediante fragmentos estructurales o hashes para evitar
inflar el repositorio.

### Pruebas generativas y fuzzing

Generar combinaciones de bloques, comentarios, espacios, modos y numeraciones
malformadas. La propiedad principal sería: entradas fuera del formato validado
nunca producen una transformación aplicada.

### Comparador semántico

Comprobar automáticamente que toda trayectoria original aparece exactamente una
vez en la salida, pertenece al mismo objeto y solo cambia de posición como bloque
autorizado. También debería verificar el estado modal vigente en cada movimiento
con extrusión.

### Matriz de compatibilidad

Registrar por versión de Cura, firmware, impresora, material y perfil qué pruebas
fueron solo estáticas y cuáles tuvieron una ejecución física supervisada. Evitar
generalizar el resultado de una Ender 3 Pro a otras máquinas.

## Experiencia de uso

- mostrar en Cura una explicación precisa de cada rechazo y cómo corregirlo;
- añadir un modo “solo validar” que no reordene;
- generar nombres/versiones reconocibles en los comentarios del archivo;
- advertir si el mismo G-code ya fue procesado;
- preparar una vista previa del orden de objetos y las transiciones;
- ofrecer un checklist previo a una prueba física supervisada.

## Registro de ideas provenientes de pruebas físicas

- **Resuelto:** restaurar `M83` después del `G90` insertado.
- **Resuelto:** distinguir un cambio térmico real de una repetición del objetivo
  vigente, como `M104 S220` cuando el hotend ya está solicitado a 220 °C. Esta
  repetición se conserva y no exige un comando equivalente en cada capa común.
- **Implementado y validado físicamente en la configuración probada:** diferir
  el cambio de temperatura normal `M104` hasta la última capa común y omitir
  `M109`/`M190` únicamente cuando el objetivo exacto ya está solicitado y
  confirmado sin cambios intermedios. Una impresión supervisada de 16 objetos
  completó correctamente la fase común y la terminación secuencial.
- **Pendiente:** reducir el riesgo de rezume cuando una espera térmica sea
  realmente necesaria mediante una zona de estacionamiento validada.
- **Pendiente:** recopilar resultado, fotografías y firmware exacto de cada
  prueba sin almacenar información privada por defecto.
