"""Small, dependency-free catalogue for calculation-facing text.

Numeric fields and stable machine codes remain language-independent.  Source
metadata supplied by an importer is intentionally not translated here.
"""
from __future__ import annotations


SUPPORTED_LOCALES = ("ru", "kk", "en")

MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "supplier_missing": "Поставщик не указан: проверьте позицию в очереди без назначенного поставщика",
        "spike_reason": "Разовый выброс за день: преобладает один клиент или заказ; повторного пика в том же месяце нет",
        "document_spikes": "{count} разовых всплесков связаны с номером документа, а не с идентификатором клиента; проверьте исключения в деталях",
        "sparse_stockout": "Для {days} дней отсутствия товара использована общая медиана: наблюдений за тот же день недели меньше {minimum}",
        "no_sales": "Нет истории продаж с датами: прогноз спроса построить невозможно",
        "no_positive_demand": "В истории нет положительного спроса: без дополнительных данных рекомендация равна нулю",
        "urgency_critical": "критическая",
        "urgency_high": "высокая",
        "urgency_normal": "обычная",
        "urgency_covered": "запас покрывает спрос",
        "source_synthetic": "синтетические данные",
        "source_uploaded": "загруженные данные",
        "no_stockout_forecast": "не ожидается в пределах горизонта расчёта",
        "explanation": (
            "Источник: {source}. Прогноз спроса {forecast_need:.2f} ед. на {horizon} дн. "
            "(поставка {lead_days} + пересмотр {review_days} + страховой запас {safety_days}); "
            "остаток {on_hand:.2f}; поступления до конца горизонта {inbound_in_horizon:.2f}; "
            "максимальный дефицит по датам {net_need:.2f} "
            "(дефицит в конце горизонта {terminal_net_need:.2f}); "
            "минимальная партия {moq:g}, кратность упаковки {pack_size:g}; рекомендуем {recommended:g}. "
            "Скорректированный исторический спрос {adjusted_daily:.3f} ед./день; "
            "оценка упущенного спроса {lost_total:.2f} ед.; "
            "исключено выбросов {excluded_quantity:.2f} ед.; "
            "сезонность ×{mean_seasonality:.3f}, тренд ×{trend_factor:.3f}, прирост ×{growth_factor:.3f}. "
            "Срочность: {urgency}; ожидаемый дефицит без нового заказа: {stockout}."
        ),
        "future_sales": "Не учтено продаж после расчётной даты {as_of}: {count}",
        "unknown_sales": "Не учтено продаж для неизвестного артикула или склада: {count}",
        "future_stockout": "Период отсутствия товара stockouts[{index}] начинается после расчётной даты {as_of}; не учтён",
        "unknown_stockout": "Период отсутствия товара stockouts[{index}]: неизвестный артикул/склад {sku}/{warehouse}; не учтён",
        "past_inbound": "Поставка inbound[{index}] с датой {eta} не позже расчётной даты; не учтена в прогнозе",
        "unknown_inbound": "Поставка inbound[{index}]: неизвестный артикул/склад {sku}/{warehouse}; не учтена",
    },
    "kk": {
        "supplier_missing": "Жеткізуші көрсетілмеген: тағайындалмаған позицияны тексеріңіз",
        "spike_reason": "Бір күндік бір реттік ауытқу: бір клиент не тапсырыс басым, сол айда қайталанбаған",
        "document_spikes": "{count} бір реттік ауытқу клиент идентификаторына емес, құжат нөміріне негізделген; алып тастауларды тексеріңіз",
        "sparse_stockout": "Тауар болмаған {days} күн үшін жалпы медиана қолданылды: сол апта күніне қатысты бақылаулар {minimum} санынан аз",
        "no_sales": "Күні көрсетілген сату тарихы жоқ: сұранысты болжау мүмкін емес",
        "no_positive_demand": "Тарихта оң сұраныс жоқ: қосымша деректерсіз ұсынылған тапсырыс нөлге тең",
        "urgency_critical": "аса шұғыл",
        "urgency_high": "жоғары",
        "urgency_normal": "қалыпты",
        "urgency_covered": "қор сұранысты өтейді",
        "source_synthetic": "синтетикалық деректер",
        "source_uploaded": "жүктелген деректер",
        "no_stockout_forecast": "есептеу көкжиегінде күтілмейді",
        "explanation": (
            "Дереккөз: {source}. {horizon} күнге болжамды сұраныс {forecast_need:.2f} дана "
            "(жеткізу {lead_days} + қайта қарау {review_days} + сақтандыру қоры {safety_days}); "
            "қолдағы қор {on_hand:.2f}; көкжиек соңына дейінгі түсім {inbound_in_horizon:.2f}; "
            "күндер бойынша ең үлкен тапшылық {net_need:.2f} "
            "(көкжиек соңындағы тапшылық {terminal_net_need:.2f}); "
            "ең аз партия {moq:g}, қаптама еселігі {pack_size:g}; ұсынылатын саны {recommended:g}. "
            "Түзетілген тарихи сұраныс {adjusted_daily:.3f} дана/күн; "
            "өтелмеген сұраныс бағасы {lost_total:.2f} дана; "
            "алынып тасталған ауытқулар {excluded_quantity:.2f} дана; "
            "маусымдылық ×{mean_seasonality:.3f}, тренд ×{trend_factor:.3f}, өсім ×{growth_factor:.3f}. "
            "Шұғылдық: {urgency}; жаңа тапсырыссыз күтілетін тапшылық: {stockout}."
        ),
        "future_sales": "Есептеу күнінен {as_of} кейінгі сатулар есепке алынбады: {count}",
        "unknown_sales": "Белгісіз артикул не қойма бойынша сатулар есепке алынбады: {count}",
        "future_stockout": "Тауар болмау кезеңі stockouts[{index}] есептеу күнінен {as_of} кейін басталады; есепке алынбады",
        "unknown_stockout": "Тауар болмау кезеңі stockouts[{index}]: белгісіз артикул/қойма {sku}/{warehouse}; есепке алынбады",
        "past_inbound": "inbound[{index}] түсімі {eta} күнімен есептеу күнінен кеш емес; болжамға енгізілмеді",
        "unknown_inbound": "inbound[{index}] түсімі: белгісіз артикул/қойма {sku}/{warehouse}; есепке алынбады",
    },
    "en": {
        "supplier_missing": "Supplier is missing: review this unassigned item",
        "spike_reason": "One-day outlier: one customer or order dominates, with no repeat peak in the same month",
        "document_spikes": "{count} one-off spikes were inferred from document numbers, not customer IDs; review exclusions in the details",
        "sparse_stockout": "A global median was used for {days} stockout days: fewer than {minimum} observations for the same weekday",
        "no_sales": "No dated sales history: demand cannot be forecast",
        "no_positive_demand": "No positive demand in the history: recommendation is zero without additional data",
        "urgency_critical": "critical",
        "urgency_high": "high",
        "urgency_normal": "normal",
        "urgency_covered": "stock covers demand",
        "source_synthetic": "synthetic data",
        "source_uploaded": "uploaded data",
        "no_stockout_forecast": "not expected within the planning horizon",
        "explanation": (
            "Source: {source}. Forecast demand {forecast_need:.2f} units over {horizon} days "
            "(lead time {lead_days} + review {review_days} + safety cover {safety_days}); "
            "on hand {on_hand:.2f}; receipts within horizon {inbound_in_horizon:.2f}; "
            "maximum dated shortfall {net_need:.2f} "
            "(end-of-horizon shortfall {terminal_net_need:.2f}); "
            "minimum order {moq:g}, pack multiple {pack_size:g}; recommend {recommended:g}. "
            "Adjusted historical demand {adjusted_daily:.3f} units/day; "
            "estimated lost demand {lost_total:.2f} units; "
            "excluded outliers {excluded_quantity:.2f} units; "
            "seasonality ×{mean_seasonality:.3f}, trend ×{trend_factor:.3f}, growth ×{growth_factor:.3f}. "
            "Urgency: {urgency}; expected stockout without a new order: {stockout}."
        ),
        "future_sales": "Sales after calculation date {as_of} ignored: {count}",
        "unknown_sales": "Sales for unknown SKU or warehouse ignored: {count}",
        "future_stockout": "Stockout interval stockouts[{index}] starts after calculation date {as_of}; ignored",
        "unknown_stockout": "Stockout interval stockouts[{index}]: unknown SKU/warehouse {sku}/{warehouse}; ignored",
        "past_inbound": "Inbound receipt inbound[{index}] dated {eta} is not after the calculation date; excluded from forecast",
        "unknown_inbound": "Inbound receipt inbound[{index}]: unknown SKU/warehouse {sku}/{warehouse}; ignored",
    },
}


def normalize_locale(value: object) -> str:
    """Reject unsupported locale IDs instead of silently mislabelling output."""
    if not isinstance(value, str) or value not in SUPPORTED_LOCALES:
        raise ValueError("settings.locale must be one of: ru, kk, en")
    return value


def message(locale: str, key: str, **values: object) -> str:
    return MESSAGES[locale][key].format(**values)
