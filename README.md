# MapReduce

Esta es una aplicación de ejemplo que procesa datos de disparos de fútbol con un patrón MapReduce distribuido y provee una interfaz web para visualizar estadísticas y zonas de disparo.

## Estructura del proyecto

- `main.py`: punto de entrada principal para ejecución local y generación de la base de datos.
- `master.py`: coordina la ejecución distribuida, distribuye tareas de mapeo y reducción entre los workers, y arma el resultado final.
- `worker.py`: define un worker FastAPI que recibe tareas de `map` y `reduce` desde el master.
- `server.py`: servidor HTTP que expone la interfaz web y las APIs para filtros, datos y estado de jobs.
- `mapper.py`: lógica del mapper que transforma cada fila de disparo en claves y métricas intermedias.
- `reducer.py`: lógica del reducer que agrega métricas por clave.
- `metrics.py`: clase `ShotMetrics` para acumular disparos, goles, xG y otras métricas.
- `docker-compose.yml`: define los servicios `master` y los workers Docker para ejecutar el sistema distribuido.
- `shots_dataset_cleaned.csv`: dataset de disparos utilizado como fuente de datos.
- `web/`: carpeta con la interfaz de usuario.
  - `web/index.html`: página web principal.
  - `web/styles.css`: estilos de la interfaz.
  - `web/app.js`: lógica del frontend, llamadas a la API y renderizado.

## Cómo funciona

1. `master.py` lee el CSV en chunks y envía cada chunk a un worker para el `map`.
2. Cada worker usa `mapper.py` para convertir filas de disparos en pares `(clave, métricas)`.
3. El master recibe los resultados mapeados, agrupa y reparte las claves entre workers para la fase de `reduce`.
4. Cada worker usa `reducer.py` para sumar métricas de las claves asignadas.
5. El master construye el resultado final y el servidor web lo sirve a través de `server.py`.

## Flujo de ejecución

- El usuario accede a la interfaz web y solicita un análisis o cambia los filtros.
- `web/app.js` envía una petición al servidor de `server.py`, típicamente a `/api/start_job`.
- `server.py` delega la carga de trabajo a `master.py` ejecutando `run_distributed_mapreduce_background(...)` en un hilo separado.
- `master.py` lee `shots_dataset_cleaned.csv` en trozos controlados (`chunks`), para no procesar todo el archivo de una vez.
- Cada chunk se envía a uno de los workers vía `POST /map`.
- En el worker, `worker.py` recibe ese chunk y ejecuta `mapper.py`:
  - transforma cada fila en un diccionario tipado;
  - calcula la zona de la cancha (`grid`) y otras claves como `player`, `shot_type`, `situation`, `global`;
  - acumula métricas con `ShotMetrics`.
- El worker aplica un combiner local para agrupar claves iguales dentro del mismo chunk y devuelve una lista de objetos JSON como:
  - `key`: clave serializada (`["grid", 6, 3]`, `['player', 'Lionel Messi']`, etc.)
  - `metrics`: totales de `shots`, `goals`, `misses`, `xg_sum`
- El master recibe todos los resultados mapeados y hace la fase de shuffle:
  - convierte las claves en una partición estable con `hash(key)`;
  - reparte los elementos para que cada worker reciba todas las entradas de las mismas claves.
- El master envía cada partición a `POST /reduce` en los workers.
- Cada worker ejecuta `reducer.py`, que agrupa los pares por clave y suma las métricas usando `ShotMetrics.merge()`.
- Los workers devuelven resultados reducidos: claves únicas con métricas consolidadas.
- El master recibe esos resultados reducidos y arma el JSON final:
  - datos de `grid` por zona,
  - estadísticas globales,
  - top jugadores,
  - desglose por tipo de tiro y situación.
- El frontend consulta el estado del job y el resultado final para renderizar los mapas, tarjetas y tablas.

## Uso básico

Para agregar más workers, crea nuevos servicios `worker4`, `worker5`, etc. en `docker-compose.yml` y añade sus URLs a la variable de entorno `WORKERS` en el servicio `master`.

## Notas

- El dataset se carga desde `shots_dataset_cleaned.csv`.
- Los filtros disponibles se extraen de la base de datos o del dataset.
- El código actual usa FastAPI por worker y un servidor HTTP básico para la UI.
