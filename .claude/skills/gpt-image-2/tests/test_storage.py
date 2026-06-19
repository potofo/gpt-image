"""画像保存（storage）のテスト。"""
import os
import re

from storage import save_images


def test_saves_single_image_returns_absolute_path(tmp_path):
    paths = save_images([b"\x89PNG-data"], str(tmp_path), "png")
    assert len(paths) == 1
    assert os.path.isabs(paths[0])
    assert os.path.exists(paths[0])
    with open(paths[0], "rb") as f:
        assert f.read() == b"\x89PNG-data"


def test_naming_convention(tmp_path):
    paths = save_images([b"x"], str(tmp_path), "png")
    name = os.path.basename(paths[0])
    assert re.fullmatch(r"gpt-image-2_\d{8}T\d{6}\d*_0\.png", name), name


def test_multiple_images_sequential(tmp_path):
    paths = save_images([b"a", b"b", b"c"], str(tmp_path), "png")
    assert len(paths) == 3
    indices = [int(re.search(r"_(\d+)\.png$", p).group(1)) for p in paths]
    assert indices == [0, 1, 2]
    # 中身が index 順に対応している
    for content, p in zip([b"a", b"b", b"c"], paths):
        with open(p, "rb") as f:
            assert f.read() == content


def test_jpeg_extension(tmp_path):
    paths = save_images([b"j"], str(tmp_path), "jpeg")
    assert paths[0].endswith(".jpg")


def test_creates_output_dir_if_missing(tmp_path):
    target = tmp_path / "nested" / "out"
    paths = save_images([b"x"], str(target), "png")
    assert os.path.exists(paths[0])
    assert os.path.isdir(str(target))
