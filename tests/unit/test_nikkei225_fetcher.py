"""
Nikkei225Fetcher ユニットテスト

テスト観点:
- 手動CSV（cp932）からの正常読み込み
- カラム名の柔軟マッチング
- エンコーディング自動検出
- フォールバック（手動CSV → キャッシュ → RuntimeError）
- 銘柄数不足時の安全ガード
- キャッシュの保存・読み込み
- コード正規化（.0除去、アルファベット末尾）
"""
import pytest
import pandas as pd
from pathlib import Path

from src.low_hunter.nikkei225_fetcher import Nikkei225Fetcher


@pytest.fixture
def tmp_project(tmp_path):
    cache_dir = tmp_path / "data"
    cache_dir.mkdir()
    return tmp_path, cache_dir


def _create_csv(path, rows, encoding="cp932"):
    lines = [",".join(row) for row in rows]
    path.write_text("\n".join(lines), encoding=encoding)


def _gen_225(header=None):
    header = header or ["銘柄コード", "銘柄名", "業種"]
    rows = [header]
    for i in range(225):
        rows.append([str(1000 + i), f"テスト銘柄{i}", "業種"])
    return rows


class TestLoadManualCsv:
    def test_cp932(self, tmp_project):
        root, cache = tmp_project
        _create_csv(root / "日経平均225構成銘柄.csv", _gen_225(), "cp932")
        result = Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert len(result) == 225
        assert result[0] == ("1000", "テスト銘柄0")

    def test_utf8(self, tmp_project):
        root, cache = tmp_project
        _create_csv(root / "日経平均225構成銘柄.csv", _gen_225(), "utf-8")
        result = Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert len(result) == 225

    def test_utf8_sig(self, tmp_project):
        root, cache = tmp_project
        _create_csv(root / "日経平均225構成銘柄.csv", _gen_225(), "utf-8-sig")
        result = Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert len(result) == 225


class TestColumnMapping:
    def test_alt_columns(self, tmp_project):
        root, cache = tmp_project
        _create_csv(
            root / "日経平均225構成銘柄.csv",
            _gen_225(["コード", "銘柄", "業種"]),
            "cp932",
        )
        result = Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert len(result) == 225

    def test_unknown_columns_raises(self, tmp_project):
        root, cache = tmp_project
        _create_csv(
            root / "日経平均225構成銘柄.csv",
            _gen_225(["x", "y", "z"]),
            "cp932",
        )
        with pytest.raises(RuntimeError):
            Nikkei225Fetcher(str(root), str(cache)).fetch()


class TestFallback:
    def test_no_csv_uses_cache(self, tmp_project):
        root, cache = tmp_project
        rows = [(str(5000 + i), f"C{i}") for i in range(225)]
        df = pd.DataFrame(rows, columns=["code", "name"])
        df.to_csv(cache / "nikkei225_cache.csv", index=False, encoding="utf-8-sig")
        result = Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert len(result) == 225

    def test_nothing_raises(self, tmp_project):
        root, cache = tmp_project
        with pytest.raises(RuntimeError):
            Nikkei225Fetcher(str(root), str(cache)).fetch()


class TestSafetyGuard:
    def test_too_few_stocks(self, tmp_project):
        root, cache = tmp_project
        header = ["銘柄コード", "銘柄名", "業種"]
        rows = [header] + [[str(i), f"S{i}", "X"] for i in range(50)]
        _create_csv(root / "日経平均225構成銘柄.csv", rows, "cp932")
        with pytest.raises(RuntimeError):
            Nikkei225Fetcher(str(root), str(cache)).fetch()


class TestCacheSaveLoad:
    def test_cache_created(self, tmp_project):
        root, cache = tmp_project
        _create_csv(root / "日経平均225構成銘柄.csv", _gen_225(), "cp932")
        Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert (cache / "nikkei225_cache.csv").exists()
        df = pd.read_csv(cache / "nikkei225_cache.csv", dtype=str)
        assert len(df) == 225


class TestCodeNormalization:
    def test_float_code(self, tmp_project):
        root, cache = tmp_project
        header = ["銘柄コード", "銘柄名", "業種"]
        rows = [header] + [[f"{6000+i}.0", f"F{i}", "D"] for i in range(225)]
        _create_csv(root / "日経平均225構成銘柄.csv", rows, "utf-8")
        result = Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert result[0][0] == "6000"

    def test_alpha_suffix(self, tmp_project):
        root, cache = tmp_project
        header = ["銘柄コード", "銘柄名", "業種"]
        rows = [header] + [[str(7000+i), f"N{i}", "E"] for i in range(224)]
        rows.append(["123A", "Alpha", "E"])
        _create_csv(root / "日経平均225構成銘柄.csv", rows, "utf-8")
        result = Nikkei225Fetcher(str(root), str(cache)).fetch()
        assert "123A" in [r[0] for r in result]
