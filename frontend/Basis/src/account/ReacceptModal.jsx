/**
 * Повторный акцепт условий для тех, кто зарегистрировался ДО публикации документов.
 *
 * ЗАЧЕМ. Оферта, политика и документ об аналитике опубликованы 06.09.2026, галочка на
 * форме регистрации появилась тогда же. Люди, зарегистрировавшиеся раньше, никаких
 * условий не принимали — доказательства акцепта по ним нет вовсе. Пока они продолжают
 * пользоваться платформой, отношения формально не оформлены: непонятно, на каких
 * условиях оказывается услуга и что человеку показывали про характер аналитики.
 *
 * Окно показывается один раз — при первом входе после выкатки — и пишет ту же запись в
 * `consents`, что и регистрация. Нового согласия на обработку персональных данных оно НЕ
 * собирает: основание обработки — договор (см. docs/legal/02, раздел 5).
 *
 * 🔴 ОКНО НЕ БЛОКИРУЕТ ПЛАТФОРМУ НАСМЕРТЬ. Кнопка «Позже» закрывает его до следующего
 * захода: запирать человека, который уже пользуется сервисом, в модальном окне — это
 * навязывание, а не согласие. Запись появится, когда он нажмёт «Принимаю».
 */
import React, { useState } from "react";

const LEGAL_VERSION = "1.0";

export default function ReacceptModal({ token, apiUrl, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${apiUrl}/api/consents`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ kind: "offer_accept", version: LEGAL_VERSION, granted: true }),
      });
      if (!r.ok) throw new Error("Не удалось сохранить. Попробуйте ещё раз.");
      onDone(true);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <div className="reaccept-backdrop" role="dialog" aria-modal="true" aria-labelledby="reaccept-title">
      <div className="reaccept-card">
        <h2 id="reaccept-title" className="reaccept-title">Мы опубликовали условия использования</h2>
        <p className="reaccept-text">
          Раньше на платформе не было опубликованных условий — теперь есть. Ничего не
          изменилось в том, как вы пользуетесь Basis: документы описывают то, что уже
          происходит, — какие данные мы обрабатываем, как работает оплата и возврат и
          почему наша аналитика не является индивидуальной инвестиционной рекомендацией.
        </p>
        <ul className="reaccept-links">
          <li><a href="/offer/" target="_blank" rel="noopener">Публичная оферта</a></li>
          <li><a href="/privacy/" target="_blank" rel="noopener">Политика обработки персональных данных</a></li>
          <li><a href="/about-analytics/" target="_blank" rel="noopener">Об аналитике Basis</a></li>
        </ul>
        {error && <p className="reaccept-error" role="alert">{error}</p>}
        <div className="reaccept-actions">
          <button type="button" className="reaccept-primary" onClick={accept} disabled={busy}>
            {busy ? "Сохраняю…" : "Принимаю"}
          </button>
          <button type="button" className="reaccept-later" onClick={() => onDone(false)} disabled={busy}>
            Позже
          </button>
        </div>
      </div>
    </div>
  );
}
