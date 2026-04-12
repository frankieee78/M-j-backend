"""Backend tests for Czech Financial Literacy App"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def test_user():
    """Create a test user and return user data"""
    device_id = f"TEST_{uuid.uuid4().hex}"
    res = requests.post(f"{BASE_URL}/api/users", json={
        "username": "TEST_User",
        "device_id": device_id
    })
    assert res.status_code == 200
    user = res.json()
    yield user
    # No cleanup needed - test users are prefixed with TEST_

class TestUserAPI:
    """User registration and retrieval tests"""

    def test_create_user_success(self):
        device_id = f"TEST_{uuid.uuid4().hex}"
        res = requests.post(f"{BASE_URL}/api/users", json={
            "username": "TEST_NewUser",
            "device_id": device_id
        })
        assert res.status_code == 200
        data = res.json()
        assert "user_id" in data
        assert data["username"] == "TEST_NewUser"
        assert data["xp"] == 0
        assert data["level"] == 1
        assert data["streak"] == 0
        assert data["badges"] == []
        assert data["completed_lessons"] == []
        print("PASS: create_user_success")

    def test_get_existing_user_by_device_id(self):
        """Same device_id returns existing user"""
        device_id = f"TEST_{uuid.uuid4().hex}"
        res1 = requests.post(f"{BASE_URL}/api/users", json={
            "username": "TEST_Same", "device_id": device_id
        })
        res2 = requests.post(f"{BASE_URL}/api/users", json={
            "username": "TEST_Other", "device_id": device_id
        })
        assert res1.json()["user_id"] == res2.json()["user_id"]
        print("PASS: get_existing_user_by_device_id")

    def test_get_user_by_id(self, test_user):
        res = requests.get(f"{BASE_URL}/api/users/{test_user['user_id']}")
        assert res.status_code == 200
        data = res.json()
        assert data["user_id"] == test_user["user_id"]
        print("PASS: get_user_by_id")

    def test_get_user_not_found(self):
        res = requests.get(f"{BASE_URL}/api/users/nonexistent-user-id")
        assert res.status_code == 404
        print("PASS: get_user_not_found")


class TestLessonsAPI:
    """Lesson data tests"""

    def test_get_lessons_returns_6_categories(self):
        res = requests.get(f"{BASE_URL}/api/lessons")
        assert res.status_code == 200
        categories = res.json()
        assert len(categories) == 6
        print(f"PASS: get_lessons returns {len(categories)} categories")

    def test_lessons_structure(self):
        res = requests.get(f"{BASE_URL}/api/lessons")
        categories = res.json()
        for cat in categories:
            assert "name" in cat
            assert "emoji" in cat
            assert "lessons" in cat
            assert len(cat["lessons"]) == 3
        print("PASS: lessons_structure - each category has 3 lessons")

    def test_category_names(self):
        res = requests.get(f"{BASE_URL}/api/lessons")
        categories = res.json()
        names = [c["name"] for c in categories]
        expected = ["Základy", "Spoření", "Dluhy", "Investování", "Daně", "Pokročilé"]
        for exp in expected:
            assert exp in names, f"Missing category: {exp}"
        print("PASS: category_names - all 6 expected categories present")

    def test_get_specific_lesson(self):
        res = requests.get(f"{BASE_URL}/api/lessons/cat1_l1")
        assert res.status_code == 200
        lesson = res.json()
        assert lesson["lesson_id"] == "cat1_l1"
        assert "questions" in lesson
        assert len(lesson["questions"]) == 5
        print("PASS: get_specific_lesson cat1_l1 has 5 questions")

    def test_get_lesson_not_found(self):
        res = requests.get(f"{BASE_URL}/api/lessons/nonexistent")
        assert res.status_code == 404
        print("PASS: get_lesson_not_found")


class TestProgressAPI:
    """Progress recording tests"""

    def test_record_progress(self, test_user):
        res = requests.post(f"{BASE_URL}/api/progress", json={
            "user_id": test_user["user_id"],
            "lesson_id": "cat1_l1",
            "correct_count": 4,
            "total_questions": 5
        })
        assert res.status_code == 200
        data = res.json()
        assert "xp_earned" in data
        assert "new_xp" in data
        assert "streak" in data
        assert data["streak"] == 1
        print(f"PASS: record_progress - XP earned: {data['xp_earned']}, new_xp: {data['new_xp']}")

    def test_progress_awards_badge(self, test_user):
        """First lesson completion should award prvni_lekce badge"""
        # User already completed one lesson above
        res = requests.get(f"{BASE_URL}/api/users/{test_user['user_id']}")
        user = res.json()
        assert "prvni_lekce" in user["badges"]
        print("PASS: progress_awards_badge - prvni_lekce badge awarded")

    def test_progress_updates_xp(self, test_user):
        """XP should increase after lesson"""
        res = requests.get(f"{BASE_URL}/api/users/{test_user['user_id']}")
        user = res.json()
        assert user["xp"] > 0
        print(f"PASS: progress_updates_xp - XP: {user['xp']}")

    def test_progress_invalid_user(self):
        res = requests.post(f"{BASE_URL}/api/progress", json={
            "user_id": "nonexistent",
            "lesson_id": "cat1_l1",
            "correct_count": 3,
            "total_questions": 5
        })
        assert res.status_code == 404
        print("PASS: progress_invalid_user returns 404")


class TestLeaderboardAPI:
    """Leaderboard tests"""

    def test_get_leaderboard(self):
        res = requests.get(f"{BASE_URL}/api/leaderboard")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        print(f"PASS: get_leaderboard - {len(data)} users")

    def test_leaderboard_structure(self):
        res = requests.get(f"{BASE_URL}/api/leaderboard")
        users = res.json()
        if len(users) > 0:
            u = users[0]
            assert "user_id" in u
            assert "username" in u
            assert "xp" in u
            assert "level" in u
        print("PASS: leaderboard_structure")

    def test_leaderboard_sorted_by_xp(self):
        res = requests.get(f"{BASE_URL}/api/leaderboard")
        users = res.json()
        if len(users) > 1:
            xps = [u["xp"] for u in users]
            assert xps == sorted(xps, reverse=True), "Leaderboard not sorted by XP desc"
        print("PASS: leaderboard_sorted_by_xp")


class TestBadgesAPI:
    """Badges endpoint tests"""

    def test_get_badges(self):
        res = requests.get(f"{BASE_URL}/api/badges")
        assert res.status_code == 200
        badges = res.json()
        assert "prvni_lekce" in badges
        assert "vsechny_lekce" in badges
        print(f"PASS: get_badges - {len(badges)} badges defined")
