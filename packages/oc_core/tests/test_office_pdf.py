from oc_core.converters.office_pdf import find_soffice


def test_find_soffice_returns_str_or_none():
    path = find_soffice()
    assert path is None or isinstance(path, str)
