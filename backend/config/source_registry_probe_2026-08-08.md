# Проверка адресов реестра — 2026-08-08

> Прогон по 520 адресам из `source_registry_*.md`, у которых стоял `unknown` или не было
> отметки о доступности. Проверялось С ДЕВ-МАШИНЫ (не-РФ IP): HTTP-код и размер тела.
> 🔴 Это ПОЛОВИНА картины: доступность зависит от того, откуда идёшь (worldsteel с ноутбука
> давал 000, с боевого сервера отдаёт 10 записей; eia_press — наоборот). Повторная проверка
> с боя — через `POST /api/debug/probe-urls`.

## Итог: живых 355, «200 но заглушка» 15, ошибок 47, молчат 103

**Главное:** 68% адресов, помеченных в реестре как непроверенные, ОКАЗАЛИСЬ ЖИВЫМИ.
Реестр недооценивал доступность — вердикты в нём консервативнее реальности.

## Молчат с не-РФ IP (вероятен гео-блок — перепроверить с боевого сервера)

Среди них `cbr.ru`, который мы ЗАВЕДОМО успешно опрашиваем с боя. Значит большая часть
этого списка — ложно-мёртвые, и с Timeweb они откроются.

| Хост | Адресов |
|---|---|
| `spimex.com` | 6 |
| `www.atsenergo.ru` | 6 |
| `fas.gov.ru` | 5 |
| `company.rzd.ru` | 5 |
| `favt.gov.ru` | 3 |
| `fred.stlouisfed.org` | 3 |
| `ir.ozon.com` | 3 |
| `mcx.gov.ru` | 3 |
| `minpromtorg.gov.ru` | 3 |
| `www.cbr.ru` | 3 |
| `minstroyrf.gov.ru` | 2 |
| `www.aoosk.ru` | 2 |
| `www.energia.ru` | 2 |
| `www.interrao.ru` | 2 |
| `www.tbank.ru` | 2 |
| `www.morvesti.ru` | 1 |
| `<city>.tns-e.ru` | 1 |
| `asv.org.ru` | 1 |
| `cargo.rzd.ru` | 1 |
| `customs.gov.ru` | 1 |
| `digital.gov.ru` | 1 |
| `ffoms.gov.ru` | 1 |
| `gisp.gov.ru` | 1 |
| `ir.gazprom-neft.ru` | 1 |
| `mechel.ru` | 1 |
| `mgts.ru` | 1 |
| `minfin.gov.ru` | 1 |
| `mmk-coal.ru` | 1 |
| `momr.opec.org` | 1 |
| `mosenergo.gazprom.ru` | 1 |
| `peretok.ru` | 1 |
| `permenergosbyt.ru` | 1 |
| `publication.pravo.gov.ru` | 1 |
| `rnc-pharma.ru` | 1 |
| `rosreestr.gov.ru` | 1 |
| `rosseti-ural.ru` | 1 |
| `rps.ru` | 1 |
| `ruslom.com` | 1 |
| `rusprodsouz.ru` | 1 |
| `samolet.group` | 1 |
| `spp-union.ru` | 1 |
| `tatcenter.ru` | 1 |
| `www.acra-ratings.ru` | 1 |
| `www.avangard.ru` | 1 |
| `www.aviaport.ru` | 1 |
| `www.dsm.ru` | 1 |
| `www.dvec.ru` | 1 |
| `www.economy.gov.ru` | 1 |
| `www.energosale34.ru` | 1 |
| `www.fsk-ees.ru` | 1 |
| `www.gazprom-neft.ru` | 1 |
| `www.gazprom.ru` | 1 |
| `www.himkurier.ru` | 1 |
| `www.insur-info.ru` | 1 |
| `www.itek.ru` | 1 |
| `www.morflot.gov.ru` | 1 |
| `www.mrsk-cp.ru` | 1 |
| `www.np-sr.ru` | 1 |
| `www.rospotrebnadzor.ru` | 1 |
| `www.rosseti-sib.ru` | 1 |
| `www.sberbank.com` | 1 |
| `www.sibur.ru` | 1 |
| `www.tatneft.ru` | 1 |
| `www.tgc-2.ru` | 1 |
| `www.vtb.ru` | 1 |
| `www.yakutskenergo.ru` | 1 |
| `xn--80apjaadd0aq.xn--p1ai` | 1 |
| `zakupki.gov.ru` | 1 |

## Отдают ошибку (антибот/доступ)

| Код | Адресов | Примеры хостов |
|---|---|---|
| 403 | 26 | astsbyt.ru, basis.ru, cherkizovo-group.com, chzpsn.ru, corp.tns-e.ru |
| 404 | 7 | datainsight.ru, plastinfo.ru, sarnpz.rosneft.ru, www.akit.ru, www.cian.ru |
| 401 | 6 | lenta.com, samolet.ru, sovcombank.ru, www.rbc.ru, www.utair.ru |
| 503 | 4 | ir.aeroflot.ru, www.aeroflot.ru, www.metalinfo.ru, www.vsmpo.ru |
| 400 | 1 | akort.ru |
| 409 | 1 | ins-union.ru |
| 302 | 1 | www.surgutneftegas.ru |
| 502 | 1 | www.uralsib.ru |

## «200», но тело меньше 2 КБ — почти наверняка заглушка или SPA

- `http://colesa.ru/`
- `https://akort.ru`
- `https://akort.ru/`
- `https://arb.ru/`
- `https://bo.nalog.gov.ru/`
- `https://mechel.ru/shareholders/disclosure/filials/`
- `https://metalexpert.com/`
- `https://rapu.ru/activemap`
- `https://www.balticexchange.com/`
- `https://www.cnt.ru/`
- `https://www.renins.ru/`
- `https://www.renins.ru/invest/shareholders/`
- `https://www.rough-polished.com/ru/`
- `https://www.rough-polished.com/ru/analytics/`
- `https://xn--80az8a.xn--d1aqf.xn--p1ai/`

## Живые (выборка первых 40 из 355)

- `http://government.ru/` — 61 КБ
- `http://grun.ru/` — 72 КБ
- `http://ir.ciangroup.ru/ru/` — 32 КБ
- `http://nssrf.ru/` — 28 КБ
- `http://www.alrosa.ru/investors/` — 117 КБ
- `http://www.rps.ru/` — 7 КБ
- `https://abraudurso.ru/investors/` — 117 КБ
- `https://adindex.ru/` — 117 КБ
- `https://aebrus.ru/ru/media/press-releases/` — 79 КБ
- `https://aebrus.ru/ru/media/press-releases/sales-of-cars-and-light-commercial-vehicles.php` — 95 КБ
- `https://alpharm.ru/` — 54 КБ
- `https://ar2022.inarctica.com/ru/corporate-governance/share-capital` — 102 КБ
- `https://ar2023.mrsk-cp.ru/` — 117 КБ
- `https://ar2023.rushydro.ru/corporate/for-shareholders-and-investors.html` — 65 КБ
- `https://ar2023.whoosh-bike.ru/pages/sovet_direktorov/` — 47 КБ
- `https://ar2024.rushydro.ru/` — 46 КБ
- `https://asros.ru/` — 77 КБ
- `https://astra.ru/investors/` — 88 КБ
- `https://ati.su/landings/price_index/` — 117 КБ
- `https://autoins.ru/` — 27 КБ
- `https://b2b-rts.ru/investors` — 117 КБ
- `https://carmoney.ru/raskrytie-informatsii/obschaya-informatsiya` — 117 КБ
- `https://cbr.ru/statistics/RSCI/activity_uk_if/stat_pif_aif/` — 48 КБ
- `https://corp.detmir.ru/` — 38 КБ
- `https://corp.detmir.ru/investors/` — 38 КБ
- `https://datainsight.ru/` — 117 КБ
- `https://delimobil.ru/` — 5 КБ
- `https://dvizhok.su/` — 59 КБ
- `https://eepir.ru/` — 117 КБ
- `https://eepir.ru/new/sbytovye-nadbavki/` — 117 КБ
- `https://energybase.ru/` — 13 КБ
- `https://energyland.info/` — 56 КБ
- `https://enplusgroup.com/ru/investors/` — 111 КБ
- `https://erzrf.ru/` — 32 КБ
- `https://erzrf.ru/issledovaniya` — 79 КБ
- `https://erzrf.ru/top-zastroyshchikov` — 117 КБ
- `https://euroetpao.ru/investors/` — 26 КБ
- `https://europlan.ru/investor/stock` — 53 КБ
- `https://fbx.freightos.com/` — 117 КБ
- `https://fishpool.eu/` — 74 КБ
