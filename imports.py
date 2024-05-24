import contextlib
import functools
import hashlib
import json
import pathlib

import keyring


def read_file_in_chunks(file_path, chunk_size=4096):
    """Generator function to read a file in chunks.

    Args:
        file_path (str): The path to the file.
        chunk_size (int, optional): The size of each chunk in bytes. Defaults to 4096 (4KB).

    Yields:
        bytes: A chunk of data from the file.
    """
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            yield chunk


consume = tuple


def hash(filename):
    """
    Return the sha-256 hash of the contents of filename.
    """
    hash = hashlib.sha256()
    consume(map(hash.update, read_file_in_chunks(filename)))
    return hash.hexdigest()


class LocalStore:
    root = pathlib.Path('~/Library/Caches/coherent imports').expanduser()
    root.mkdir(parents=True, exist_ok=True)

    def get(self, key):
        with contextlib.suppress(FileNotFoundError):
            return json.loads(self.root.joinpath(key).read_text())

    def save(self, key, value):
        self.root.joinpath(key).write_text(json.dumps(value))


def cache(key, store=LocalStore()):
    def wrap(func):
        @functools.wraps(func)
        def wrapper(arg, *args, **kwargs):
            key_ = key(arg)
            result = store.get(key=key_)
            if not result:
                result = func(arg, *args, **kwargs)
                store.save(key=key_, value=result)
            return result

        return wrapper

    return wrap


@cache(key=hash)
def compute_requirements(filename):
    direction = "Given the following Python module, what third-party (PyPI) dependencies are needed to support the imports? Please write them as a standard requirements.txt file. The result may be empty if no imports rely on dependencies. Do not include any comments in the file."
    source = pathlib.Path(filename).read_text()
    prompt = direction + '\n\n' + f'```\n{source}\n```'
    result = query_gemini(prompt)
    return list(filter(None, result.parts[0].text.strip('`').split('\n')))


def query_gemini(prompt):
    import google.generativeai as genai

    key = keyring.get_password(
        'https://generativelanguage.googleapis.com/', 'jaraco@jaraco.com'
    )
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    return model.generate_content(prompt)
