import os
import zipfile
import tarfile
import py7zr
import rarfile


def check_path_exists(file_path: str) -> bool:
    return file_path is not None and os.path.exists(file_path)


def read_text_file(file_path: str) -> str:
    with open(file_path, "r") as f:
        text = f.read()
    return text


# --- 解凍処理を行う関数 ---
def unzip_file(zip_path: str, extract_to: str) -> None:
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)


def untar_file(tar_path: str, extract_to: str) -> None:
    with tarfile.open(tar_path, "r:gz") as tar_ref:
        tar_ref.extractall(extract_to)


def untar_bz2_file(tar_bz2_path: str, extract_to: str) -> None:
    with tarfile.open(tar_bz2_path, "r:bz2") as tar_ref:
        tar_ref.extractall(extract_to)


def un7z_file(seven_z_path: str, extract_to: str) -> None:
    with py7zr.SevenZipFile(seven_z_path, mode="r") as z:
        z.extractall(path=extract_to)


def unrar_file(rar_path: str, extract_to: str) -> None:
    with rarfile.RarFile(rar_path, mode="r") as rf:
        rf.extractall(path=extract_to)


def extract_compressed_file(file_path: str, extract_to: str) -> bool:
    if not os.path.exists(file_path):
        print(f"File does not exist: {file_path}")
        return False

    # 拡張子に基づいて適切な解凍関数を呼び出す
    if file_path.endswith(".zip"):
        unzip_file(file_path, extract_to)
        return True
    elif file_path.endswith(".tar.gz") or file_path.endswith(".tgz"):
        untar_file(file_path, extract_to)
        return True
    elif file_path.endswith(".tar.bz2"):
        untar_bz2_file(file_path, extract_to)
        return True
    elif file_path.endswith(".7z"):
        un7z_file(file_path, extract_to)
        return True
    elif file_path.endswith(".rar"):
        unrar_file(file_path, extract_to)
        return True
    else:
        # 圧縮されていないファイルの場合、何もしないか、ユーザーに通知する
        print(
            f"File is not a supported compressed format or is not compressed: {file_path}"
        )
        return False
