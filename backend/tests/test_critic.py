from app.services import critic


def test_чек_листы_собираются_из_методичек_для_всех_контуров():
    for contour in critic.CONTOURS:
        text, missing = critic.checklist_text(contour)
        assert len(text) > 2000, f"{contour}: чек-лист подозрительно короткий"
        assert not missing, f"{contour}: разделы чек-листа не найдены на полке: {missing}"
        assert "Типовые ошибки" in text or "ошиб" in text.lower()


def test_счёт_нарушений_по_тяжести():
    s = critic.score([{"severity": "критично"}, {"severity": "существенно"}, {"severity": "мелочь"},
                      {"severity": "неизвестно"}])
    assert (s["critical"], s["major"], s["minor"], s["weighted"], s["clean"]) == (1, 1, 1, 6, False)
    assert critic.score([])["clean"] is True
