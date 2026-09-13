from app.services.lessons import lesson_key


def test_ключ_урока_не_зависит_от_цитаты_и_регистра():
    a = lesson_key("macro", "code 0.7 / Часть 2 п.7 (число без источника)", "blocks.inflation.level, mechanism")
    b = lesson_key("macro", "CODE 0.7 / часть 2 п.7  (число без источника)", "blocks.inflation.level; data_flags")
    assert a == b, "то же правило в том же месте — тот же урок"
    assert lesson_key("macro", "code 0.7", "blocks.credit") != a
    assert lesson_key("geo", "code 0.7", "blocks.inflation.level") != a
