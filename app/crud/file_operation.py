import os
import zipfile
import tarfile
import py7zr
import rarfile
import shutil
from fastapi import UploadFile
from typing import List


def check_path_exists(file_path: str) -> bool:
    return file_path is not None and os.path.exists(file_path)


def is_dir(dir_path: str) -> bool:
    return check_path_exists(dir_path) and os.path.isdir(dir_path)


def is_file(file_path: str) -> bool:
    return check_path_exists(file_path) and os.path.isfile(file_path)


def read_text_file(file_path: str) -> str:
    with open(file_path, "r") as f:
        text = f.read()
    return text


def write_uploaded_file(file: UploadFile, dst_file_path: str) -> None:
    """
    dst_file_pathにはファイル名まで含めた絶対パスを指定する．
    """
    with open(dst_file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)


def mkdir(dir_path: str) -> None:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def copy_file(src: str, dst: str) -> None:
    """
    引数src, dstともにファイル名まで含めたパスを指定する．
    dstに同名のファイルが存在する場合上書きする．
    ディレクトリは作成しないのでdstのディレクトリを事前に作成しておくこと．
    """
    shutil.copyfile(src, dst)


def copy_directory(src_dir: str, dst_dir: str) -> None:
    """
    src_dirで指定されたディレクトリとその中のファイルをdst_dirにコピーする．
    dst_dirが既に存在する場合は，その中身を上書きする．
    """
    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)


def rename_item(path: str, new_name: str) -> None:
    """
    pathで指定されたファイルやディレクトリをnew_nameにリネームする．
    new_nameが絶対パスの場合はそのままリネームする．
    """
    if os.path.exists(path):
        if os.path.isabs(new_name):
            new_path = new_name
        else:
            dir_name = os.path.dirname(path)
            new_path = os.path.join(dir_name, new_name)
        if not os.path.exists(new_path):
            os.rename(path, new_path)


def delete_file(file_path: str) -> None:
    if os.path.exists(file_path):
        os.remove(file_path)


def delete_dir(dir_path: str) -> None:
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)


# --- 解凍処理を行う関数 ---re
def unzip_file(zip_path: str, extract_to: str) -> List[str]:
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        extracted_items = zip_ref.namelist()
        zip_ref.extractall(extract_to)
    return extracted_items


def untar_file(tar_path: str, extract_to: str) -> List[str]:
    with tarfile.open(tar_path, "r:gz") as tar_ref:
        extracted_items = tar_ref.getnames()
        tar_ref.extractall(extract_to)
    return extracted_items


def untar_bz2_file(tar_bz2_path: str, extract_to: str) -> List[str]:
    with tarfile.open(tar_bz2_path, "r:bz2") as tar_ref:
        extracted_items = tar_ref.getnames()
        tar_ref.extractall(extract_to)
    return extracted_items


def un7z_file(seven_z_path: str, extract_to: str) -> List[str]:
    with py7zr.SevenZipFile(seven_z_path, mode="r") as z:
        extracted_items = z.getnames()
        z.extractall(path=extract_to)
    return extracted_items


def unrar_file(rar_path: str, extract_to: str) -> List[str]:
    with rarfile.RarFile(rar_path, mode="r") as rf:
        extracted_items = rf.getnames()
        rf.extractall(path=extract_to)
    return extracted_items


def extract_compressed_file(file_path: str, extract_to: str) -> List[str]:
    if not os.path.exists(file_path):
        print(f"File does not exist: {file_path}")
        return []

    # 拡張子に基づいて適切な解凍関数を呼び出す
    if file_path.endswith(".zip"):
        return unzip_file(file_path, extract_to)
    elif file_path.endswith(".tar.gz") or file_path.endswith(".tgz"):
        return untar_file(file_path, extract_to)
    elif file_path.endswith(".tar.bz2"):
        return untar_bz2_file(file_path, extract_to)
    elif file_path.endswith(".7z"):
        return un7z_file(file_path, extract_to)
    elif file_path.endswith(".rar"):
        return unrar_file(file_path, extract_to)
    else:
        # 圧縮されていないファイルの場合、何もしないか、ユーザーに通知する
        print(
            f"File is not a supported compressed format or is not compressed: {file_path}"
        )
        return []
