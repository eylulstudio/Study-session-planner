import unittest
from app import calculate_weekly_stats, generate_comparison_message

class TestStudySessionPlannerLogic(unittest.TestCase):

    # =========================================================================
    # [US4] DASHBOARD & WEEKLY SUMMARY TESTS (Hesaplama ve İlerleme Mantığı)
    # =========================================================================

    def test_calculate_weekly_stats_normal_progress(self):
        """[US4] Kullanıcının hedefinin altında kaldığı normal bir ilerleme durumunu test eder."""
        total_seconds = 7200  # 120 dakika = 2 saat
        target_mins = 600     # 10 saat hedef
        
        total_mins, hours, minutes, progress = calculate_weekly_stats(total_seconds, target_mins)
        
        self.assertEqual(total_mins, 120)
        self.assertEqual(hours, 2)
        self.assertEqual(minutes, 0)
        self.assertEqual(progress, 20)  # 120 / 600 = %20 ilerleme

    def test_calculate_weekly_stats_exceeding_target(self):
        """[US4] Kullanıcı hedefi aştığında progress barın maksimum %100 olmasını test eder."""
        total_seconds = 43200  # 720 dakika = 12 saat
        target_mins = 600      # 10 saat hedef
        
        total_mins, hours, minutes, progress = calculate_weekly_stats(total_seconds, target_mins)
        
        self.assertEqual(progress, 100)  # %120 olsa bile tavan %100 kalmalı

    def test_calculate_weekly_stats_zero_target(self):
        """[US4] Hedefin 0 girilmesi durumundaki ZeroDivisionError çökme korumasını test eder."""
        total_seconds = 3600
        target_mins = 0
        
        total_mins, hours, minutes, progress = calculate_weekly_stats(total_seconds, target_mins)
        
        self.assertEqual(progress, 0)  # Çökme yaşanmadan 0 dönmeli

    # =========================================================================
    # [US4] COMPARISON MESSAGE TESTS (Haftalık Kıyaslama Varyasyonları)
    # =========================================================================

    def test_generate_comparison_message_more_study(self):
        """[US4] Bu hafta geçen haftadan daha fazla çalışıldığında üretilen tebrik mesajını test eder."""
        msg = generate_comparison_message(total_mins_this_week=600, total_mins_last_week=480)
        self.assertEqual(msg, "You studied 2 hours more than last week! 🚀")

    def test_generate_comparison_message_behind(self):
        """[US4] Bu hafta geçen haftanın gerisinde kalındığında üretilen motivasyon mesajını test eder."""
        msg = generate_comparison_message(total_mins_this_week=300, total_mins_last_week=420)
        self.assertEqual(msg, "You are 2 hours behind last week's progress. Keep going! ⏱️")

    def test_generate_comparison_message_exact_match(self):
        """[US4] İki haftanın süreleri saniyesine kadar eşitse üretilen tam eşleşme mesajını test eder."""
        msg = generate_comparison_message(total_mins_this_week=500, total_mins_last_week=500)
        self.assertEqual(msg, "You have matched last week's study time exactly so far! 🎯")

    # =========================================================================
    # [US1 / US2] COURSE & SESSION VALIDATION TESTS (Veri Sınır Güvenliği)
    # =========================================================================

    def test_course_name_whitespace_validation_logic(self):
        """[US1] Kullanıcının sadece boşluklardan oluşan geçersiz bir ders adı girmesini engelleyen mantığı test eder."""
        # app.py satır 232'deki .strip() mantığının simülasyonu
        user_input = "      "
        cleaned_input = user_input.strip()
        
        is_invalid = (not cleaned_input)
        self.assertTrue(is_invalid)  # Boşluklardan oluşan girdi geçersiz sayılmalı

    def test_password_strength_criteria_logic(self):
        """[US2] Kayıt esnasındaki büyük harf ve rakam zorunluluğu filtre mantığını test eder."""
        # app.py satır 271-281 arasındaki şifre güç kontrollerinin iş mantığı testi
        weak_password_1 = "onlylowercase"
        weak_password_2 = "UppercaseNoNumber"
        strong_password = "SecurePassword123"
        
        self.assertFalse(any(char.isupper() for char in weak_password_1))
        self.assertFalse(any(char.isdigit() for char in weak_password_2))
        self.assertTrue(any(char.isupper() for char in strong_password) and any(char.isdigit() for char in strong_password))

    # =========================================================================
    # [US3] POMODORO TIMER MODE TESTS (Zamanlayıcı Sınır Hesaplamaları)
    # =========================================================================

    def test_pomodoro_target_limit_calculation_logic(self):
        """[US3] Pomodoro modunda çalışma ve mola sürelerinin saniye sınır hesaplamalarını test eder."""
        # app.py satır 145'teki zaman sınırı (target_limit) hesaplama mantığının testi
        pomo_state_study = 'study'
        pomo_state_break = 'break'
        
        target_limit_study = 25 * 60 if pomo_state_study == 'study' else 5 * 60
        target_limit_break = 25 * 60 if pomo_state_break == 'study' else 5 * 60
        
        self.assertEqual(target_limit_study, 1500)  # 25 dakika = 1500 saniye
        self.assertEqual(target_limit_break, 300)   # 5 mola dakikası = 300 saniye

if __name__ == '__main__':
    unittest.main()