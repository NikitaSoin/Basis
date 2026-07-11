// Cloudflare Worker — релей к minfin.gov.ru (по образцу существующего релея для
// DeepSeek/FRED, см. DEEPSEEK_BASE_URL/FRED_BASE_URL в backend/.env).
//
// ПРОБЛЕМА: прод-сервер Timeweb получает 503 от minfin.gov.ru на КАЖДЫЙ запрос
// (проверено 2026-07-12, стабильно, не разово) — с домашней сети/другого IP тот же
// запрос отдаёт 200. Похоже на бан по IP/подсети дата-центра со стороны WAF
// Минфина, не связанный с User-Agent (уже пробовали браузерный UA — не помогло).
//
// РЕШЕНИЕ: Cloudflare Worker выполняет запрос СО СВОЕЙ сети (не с IP Timeweb) —
// т.к. воркер работает на edge-сети Cloudflare, а не на арендованном сервере,
// у него другой IP/ASN, которого нет в блок-листе Минфина.
//
// КАК ПОДКЛЮЧИТЬ (владелец, доступ к Cloudflare нужен только здесь):
// 1. Cloudflare Dashboard → Workers & Pages → Create Worker.
// 2. Вставить этот код целиком, Deploy.
// 3. Скопировать URL воркера (вида https://minfin-relay.<account>.workers.dev).
// 4. В .env бэкенда (Timeweb) добавить: MINFIN_BASE_URL=https://minfin-relay.<account>.workers.dev
// 5. Перезапустить бэкенд (или дождаться следующего деплоя) — код уже готов принять
//    эту переменную (backend/app/services/macro_minfin_sync.py, _BASE).
//
// Ничего больше менять не нужно — воркер прозрачно проксирует путь+query на
// minfin.gov.ru, наш код продолжает строить обычные пути (/ru/press-center/?...).

const UPSTREAM = "https://minfin.gov.ru";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const upstreamUrl = UPSTREAM + url.pathname + url.search;

    const upstreamRequest = new Request(upstreamUrl, {
      method: request.method,
      headers: {
        // Браузерный UA — на случай, если WAF всё же дополнительно смотрит на UA
        // (не только на IP); лишним не будет.
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          + "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": request.headers.get("Accept") || "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9",
      },
      redirect: "follow",
    });

    const response = await fetch(upstreamRequest);
    // Отдаём тело+статус как есть; CORS не нужен (сервер-сервер, не браузер).
    return new Response(response.body, {
      status: response.status,
      headers: response.headers,
    });
  },
};
