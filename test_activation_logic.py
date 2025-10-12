#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой логики активации звезд
"""

def test_activation_logic():
    """Тестирует логику активации звезд"""
    MIN_INVENTORY_STARS = 100

    test_cases = [
        # (inventory_value, expected_to_activate, description)
        (50, 0, "< 100⭐ в инвентаре - не активируем"),
        (99, 0, "99⭐ в инвентаре - не активируем"),
        (100, 0, "Ровно 100⭐ - не активируем (оставляем минимум)"),
        (150, 50, "150⭐ в инвентаре - активируем 50⭐ (оставляя 100⭐)"),
        (200, 100, "200⭐ в инвентаре - активируем 100⭐ (оставляя 100⭐)"),
        (350, 250, "350⭐ в инвентаре - активируем 250⭐ (оставляя 100⭐)"),
        (1000, 900, "1000⭐ в инвентаре - активируем 900⭐ (оставляя 100⭐)"),
    ]

    print("🧪 Тестирование логики активации звезд\n")
    print(f"📋 Минимум в инвентаре: {MIN_INVENTORY_STARS}⭐\n")

    all_passed = True

    for inventory_value, expected_to_activate, description in test_cases:
        # Логика из activate_all_stars
        if inventory_value < MIN_INVENTORY_STARS:
            stars_to_activate_value = 0
        else:
            stars_to_activate_value = inventory_value - MIN_INVENTORY_STARS

        remaining_in_inventory = inventory_value - stars_to_activate_value

        passed = stars_to_activate_value == expected_to_activate
        status = "✅" if passed else "❌"

        if not passed:
            all_passed = False

        print(f"{status} {description}")
        print(f"   Инвентарь: {inventory_value}⭐")
        print(f"   Активируем: {stars_to_activate_value}⭐ (ожидалось: {expected_to_activate}⭐)")
        print(f"   Остаток: {remaining_in_inventory}⭐")
        print()

    if all_passed:
        print("✅ Все тесты пройдены!")
        print("\n💡 Логика:")
        print("   - Если < 100⭐ в инвентаре: не активируем ничего")
        print("   - Если >= 100⭐: активируем только избыток (inventory - 100⭐)")
        print("   - Всегда оставляем минимум 100⭐ в инвентаре для ценных подарков")
    else:
        print("❌ Некоторые тесты провалены!")

    return all_passed

if __name__ == "__main__":
    test_activation_logic()
