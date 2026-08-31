import configparser

def update_ini_value(ini_path, key, value, encoding="utf-8-sig"):
    config = configparser.ConfigParser(strict=False)
    config.read(ini_path, encoding=encoding)

    section_name = next((s for s in config.sections() if s.lower() == "song"), None)

    if section_name is None:
        raise KeyError(f"No [song] section found in {ini_path}")

    config[section_name][key] = str(value)

    with open(ini_path, "w", encoding=encoding) as f:
        config.write(f)