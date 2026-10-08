import pytest

from services.paths import (
    DEFAULT_IMAGE_SET,
    delete_image_set,
    delete_project,
    ensure_image_set_structure,
    image_sets_dir,
    list_image_sets,
    list_projects,
    name_collides,
    sanitize_entry_name,
)


def make_config(tmp_path, active_project="proj", active_image_set=DEFAULT_IMAGE_SET):
    return {
        "projects_dir": str(tmp_path),
        "active_project": active_project,
        "active_image_set": active_image_set,
        "active_model": "",
    }


class TestSanitizeEntryName:
    def test_replaces_spaces_with_underscore(self):
        assert sanitize_entry_name("Meu Conjunto") == "Meu_Conjunto"

    def test_strips_characters_invalid_on_windows(self):
        assert sanitize_entry_name('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"

    def test_strips_trailing_dots_and_spaces(self):
        # Windows descarta pontos/espacos nas pontas do nome de uma pasta;
        # sem isso "Teste." e "Teste" colidiriam silenciosamente no disco.
        assert sanitize_entry_name("Teste.") == "Teste"
        assert sanitize_entry_name("  Teste  ") == "Teste"

    def test_rejects_empty_or_only_invalid_content(self):
        assert sanitize_entry_name("") == ""
        assert sanitize_entry_name("   ") == ""
        assert sanitize_entry_name("...") == ""
        assert sanitize_entry_name(None) == ""

    def test_rejects_reserved_windows_device_names(self):
        assert sanitize_entry_name("con") == ""
        assert sanitize_entry_name("COM1") == ""
        assert sanitize_entry_name("LPT9") == ""

    def test_keeps_accented_and_normal_characters(self):
        assert sanitize_entry_name("Vasos_Eucalipto-v2") == "Vasos_Eucalipto-v2"
        assert sanitize_entry_name("árvore") == "árvore"


class TestNameCollides:
    def test_matches_ignoring_case(self):
        assert name_collides(["teste"], "Teste") is True
        assert name_collides(["Teste"], "TESTE") is True

    def test_no_match_for_different_names(self):
        assert name_collides(["teste"], "outro") is False
        assert name_collides([], "qualquer") is False


class TestImageSetFilesystemGuards:
    def test_ensure_image_set_structure_creates_images_dir(self, tmp_path):
        config = make_config(tmp_path)
        ensure_image_set_structure(config, "grupo_a")
        assert (image_sets_dir(config) / "grupo_a" / "images").is_dir()
        assert "grupo_a" in list_image_sets(config)

    def test_delete_image_set_rejects_default_set(self, tmp_path):
        config = make_config(tmp_path)
        with pytest.raises(ValueError):
            delete_image_set(config, DEFAULT_IMAGE_SET)

    def test_delete_image_set_rejects_unknown_name(self, tmp_path):
        config = make_config(tmp_path)
        with pytest.raises(ValueError):
            delete_image_set(config, "../outside")

    def test_delete_image_set_removes_only_target(self, tmp_path):
        config = make_config(tmp_path)
        ensure_image_set_structure(config, "grupo_a")
        ensure_image_set_structure(config, "grupo_b")
        delete_image_set(config, "grupo_a")
        remaining = list_image_sets(config)
        assert "grupo_a" not in remaining
        assert "grupo_b" in remaining


class TestProjectFilesystemGuards:
    def test_delete_project_rejects_unknown_name(self, tmp_path):
        config = make_config(tmp_path)
        with pytest.raises(ValueError):
            delete_project(config, "does_not_exist")

    def test_delete_project_rejects_empty_name(self, tmp_path):
        config = make_config(tmp_path)
        with pytest.raises(ValueError):
            delete_project(config, "")
