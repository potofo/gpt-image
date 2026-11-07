"""ファイル名タイトル導出（storage.derive_title）のテスト。"""
from storage import derive_title, save_images


def test_title_from_english_prompt():
    title = derive_title("A serene Japanese garden")
    assert title == "A-serene-Japanese-garden"


def test_title_truncated_to_max_len():
    title = derive_title("word " * 50, max_len=20)
    assert len(title) <= 20
    assert not title.endswith("-")


def test_title_removes_illegal_filename_chars():
    title = derive_title('cat: "fluffy" <v2>/test?')
    for ch in '\\/:*?"<>|':
        assert ch not in title


def test_title_keeps_japanese():
    title = derive_title("夕暮れの東京タワー 水彩画風")
    assert "夕暮れの東京タワー" in title
    assert " " not in title  # 空白はハイフンに


def test_title_empty_prompt_falls_back():
    assert derive_title("   ") == "image"
    assert derive_title('???') == "image"


def test_save_images_uses_title_in_filename(tmp_path):
    paths = save_images([b"x"], str(tmp_path), "png", title="my-garden")
    name = paths[0]
    assert "my-garden_" in name.replace("\\", "/").split("/")[-1]


def test_save_images_default_title_is_backwards_compatible(tmp_path):
    paths = save_images([b"x"], str(tmp_path), "png")
    assert "gpt-image-2_" in paths[0].replace("\\", "/").split("/")[-1]
