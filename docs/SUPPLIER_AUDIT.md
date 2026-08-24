# Аудит поставщиков LumiMatch

Дата bounded-аудита: 2026-08-24. Проверены robots.txt, sitemap, главная страница и ограниченная выборка публичных ссылок.

Сборщик использует HTTP-first и не обходит CAPTCHA, авторизацию или технические защиты. Отсутствие Product в выборке не означает, что каталог недоступен полностью.

## https://www.ambrella.biz/catalog

- robots.txt: `200`
- sitemap.xml: `ошибка/недоступен`, URL в карте: `0`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `да`
- OpenGraph/meta: `8`, canonical: `не найден`
- category links: `369`, pagination-like links: `291`, product-like links: `0`
- изображения на главной: `28`
- JavaScript: заметная JS-обвязка; JSON-LD на главной не найден
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: GV1451 BK черный IP20 10Вт 4000K 48В 120° 315*26*24 (GV1451)

## https://artelamp.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `4770`
- главная HTTP: `200`
- JSON-LD blocks на главной: `1`, Product в выборке: `да`
- OpenGraph/meta: `0`, canonical: `https://artelamp.ru/`
- category links: `113`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `52`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Кронштейн-подвес Arte Lamp EXPERT-ACCESSORIES A571006 (A571006)

## https://citilux.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `5314`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `да`
- OpenGraph/meta: `7`, canonical: `не найден`
- category links: `1`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `27`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Citilux Базель CL407033 Подвесной светильник бронза с красным абажуром (CL407033)

## https://crystallux.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `1606`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `да`
- OpenGraph/meta: `7`, canonical: `https://crystallux.ru/`
- category links: `0`, pagination-like links: `1`, product-like links: `0`
- изображения на главной: `30`
- JavaScript: заметная JS-обвязка; JSON-LD на главной не найден
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Люстра Crystal Lux FORTUNA SP158W LED GOLD (SP158W)

## https://divinare.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `997`
- главная HTTP: `200`
- JSON-LD blocks на главной: `1`, Product в выборке: `да`
- OpenGraph/meta: `0`, canonical: `https://divinare.ru/`
- category links: `64`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `32`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Токопроводящий ремень 30М Divinare DECORATO D252434 (D252434)

## https://eurosvet.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `1691`
- главная HTTP: `200`
- JSON-LD blocks на главной: `1`, Product в выборке: `да`
- OpenGraph/meta: `1`, canonical: `не найден`
- category links: `36`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `35`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Трековый светодиодный светильник для однофазного шинопровода Accord 30W белый 4200K (1 шт.) (a039567)

## https://favourite-light.com

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `0`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `нет`
- OpenGraph/meta: `5`, canonical: `не найден`
- category links: `55`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `88`
- JavaScript: заметная JS-обвязка; JSON-LD на главной не найден
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: нет
- примечание: В ограниченной выборке карточка Product не распознана; нужен site-specific adapter или browser fallback.

## https://kinklight.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `1090`
- главная HTTP: `200`
- JSON-LD blocks на главной: `1`, Product в выборке: `нет`
- OpenGraph/meta: `6`, canonical: `https://kinklight.ru/`
- category links: `0`, pagination-like links: `1`, product-like links: `84`
- изображения на главной: `313`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: нет
- примечание: В ограниченной выборке карточка Product не распознана; нужен site-specific adapter или browser fallback.

## https://lightstar.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `6867`
- главная HTTP: `200`
- JSON-LD blocks на главной: `3`, Product в выборке: `да`
- OpenGraph/meta: `8`, canonical: `https://lightstar.ru/`
- category links: `78`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `38`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Люстра подвесная Vidare (699043)

## https://shop.lussole.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `4119`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `да`
- OpenGraph/meta: `0`, canonical: `https://shop.lussole.ru/`
- category links: `60`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `210`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Какие светильники выбрать для интерьера в стиле модерн (20200528)

## https://maytoni.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `6640`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `да`
- OpenGraph/meta: `5`, canonical: `https://maytoni.ru/`
- category links: `8`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `17`
- JavaScript: заметная JS-обвязка; JSON-LD на главной не найден
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: Конвертер Wi-Fi RF DALI Цветной (RGB) - Комбинированный (MIX) (721005)

## https://mw-light.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `1691`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `нет`
- OpenGraph/meta: `0`, canonical: `https://mw-light.ru/`
- category links: `1`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `42`
- JavaScript: заметная JS-обвязка; JSON-LD на главной не найден
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: нет
- примечание: В ограниченной выборке карточка Product не распознана; нужен site-specific adapter или browser fallback.

## https://odeon-light.com

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `55`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `нет`
- OpenGraph/meta: `0`, canonical: `не найден`
- category links: `33`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `16`
- JavaScript: заметная JS-обвязка; JSON-LD на главной не найден
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: нет
- примечание: В ограниченной выборке карточка Product не распознана; нужен site-specific adapter или browser fallback.

## https://freya-light.com

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `1637`
- главная HTTP: `200`
- JSON-LD blocks на главной: `1`, Product в выборке: `да`
- OpenGraph/meta: `6`, canonical: `https://freya-light.com/`
- category links: `0`, pagination-like links: `1`, product-like links: `1`
- изображения на главной: `11`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: серия Слива / Plum (FR6137PL-L21BT1)

## https://stluce.ru

- robots.txt: `200`
- sitemap.xml: `200`, URL в карте: `0`
- главная HTTP: `200`
- JSON-LD blocks на главной: `0`, Product в выборке: `нет`
- OpenGraph/meta: `0`, canonical: `не найден`
- category links: `0`, pagination-like links: `0`, product-like links: `0`
- изображения на главной: `0`
- JavaScript: не определена по ограниченному аудиту
- Playwright: не проверялся; HTTP-first достаточен для аудита
- публичный XHR/API: не выявлялся отдельно; XHR/API не нужен для MVP-аудита
- пример распознанной карточки: нет
- примечание: В ограниченной выборке карточка Product не распознана; нужен site-specific adapter или browser fallback.
