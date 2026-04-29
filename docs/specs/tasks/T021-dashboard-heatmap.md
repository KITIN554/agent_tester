# T021 — Heatmap «сценарии × прогоны» в dashboard

## Приоритет: Важно (#6, ~1 час)

## Цель
В дашборд добавить тепловую карту: ось X — последние N прогонов корзины,
ось Y — id сценария, цвет ячейки — passed/failed/partial. Без неё нельзя
быстро увидеть «какие сценарии стабильно валятся, а какие шатают».

## Что нужно сделать

1. Новая вкладка `📊 Heatmap` (между «Парето» и «Сценарий»).
2. `dashboard/views/heatmap.py`:
   - Загрузить последние ≤30 прогонов выбранной корзины.
   - Для каждого выбрать `passed: bool` по каждому `scenario.id`.
   - Построить через `plotly.express.imshow` или `go.Heatmap`:
     - Зелёный = passed
     - Красный = failed
     - Серый = сценария не было в прогоне (когда корзина росла со временем)
   - Hover: scenario_id + run_id + passed/failed.
3. Включить эту вкладку в `dashboard/app.py`.
4. Один сюжет — одна корзина (чтобы не смешивать finance и travel).

## Acceptance criteria

- [ ] `dashboard/views/heatmap.py` создан, экспортирует `render(basket, runs)`.
- [ ] `dashboard/app.py` подключает 5-ю вкладку.
- [ ] При <2 прогонах — сообщение «нужно ≥2 прогона», без падения.
- [ ] `streamlit run dashboard/app.py` рендерит heatmap, hover работает.
- [ ] Закоммичено: `feat(dashboard): add scenario × run heatmap tab`

## Зависимости
T012 (дашборд).
