import subprocess
import time
import os
import filecmp
import pytest
import random
import string
import shutil

ROOT = "demo_root"         # fichiers servis par le serveur
DOWNLOADS = "downloads"    # fichiers reçus par le client

HOST = "::1"
PORT = 8080

SERVER_SCRIPT = "src/server.py"
CLIENT_SCRIPT = "src/client.py"
LINK_SIM = "./tests/Linksimulator-master/link_sim"


def generate_random_file(path, size_bytes):
    """Génère un fichier texte aléatoire de `size_bytes` octets"""
    chars = string.ascii_letters + string.digits + string.punctuation + " \n"
    with open(path, "w", encoding="utf-8") as f:
        remaining = size_bytes
        while remaining > 0:
            chunk_size = min(1024, remaining)
            chunk = ''.join(random.choices(chars, k=chunk_size))
            f.write(chunk)
            remaining -= chunk_size


def clean_dir(path):
    """Vide complètement un dossier sans le supprimer lui-même"""
    os.makedirs(path, exist_ok=True)

    for name in os.listdir(path):
        full = os.path.join(path, name)
        try:
            if os.path.isfile(full) or os.path.islink(full):
                os.remove(full)
            elif os.path.isdir(full):
                shutil.rmtree(full)
        except Exception as e:
            print(f"[WARN] Impossible de supprimer {full}: {e}")


# Préparation avant CHAQUE test (beaucoup plus robuste que scope="module")
@pytest.fixture(autouse=True)
def setup_demo_root():
    clean_dir(ROOT)
    clean_dir(DOWNLOADS)

    # Fichier test de 100 Ko
    generate_random_file(os.path.join(ROOT, "test.txt"), size_bytes=100 * 1024)

    # Fichier vide
    open(os.path.join(ROOT, "empty.txt"), "w").close()

    yield

    clean_dir(ROOT)
    clean_dir(DOWNLOADS)


def run_server(root=ROOT, host=HOST, port=PORT):
    """Démarre le serveur et retourne le process"""
    proc = subprocess.Popen(
        ["python3", SERVER_SCRIPT, "--root", root, host, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    time.sleep(1)  # laisse le serveur démarrer
    return proc


def run_client(save_file, url):
    """Lance le client et attend la fin"""
    result = subprocess.run(
        ["python3", CLIENT_SCRIPT, "--save", save_file, url],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("=== CLIENT STDOUT ===")
        print(result.stdout)
        print("=== CLIENT STDERR ===")
        print(result.stderr)

    assert result.returncode == 0, "Le client a crashé"


def run_linksim(args):
    """Lance LinkSimulator et retourne le process"""
    proc = subprocess.Popen(
        [LINK_SIM] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    time.sleep(1)  # laisse LinkSimulator démarrer
    return proc


def kill_proc(proc, name="PROC"):
    """Termine proprement un process et affiche stderr si utile"""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)

    try:
        stdout, stderr = proc.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        stdout, stderr = "", ""

    if stderr and stderr.strip():
        print(f"=== {name} STDERR ===")
        print(stderr)

    if stdout and stdout.strip():
        print(f"=== {name} STDOUT ===")
        print(stdout)


def assert_files_equal(file1, file2):
    assert os.path.exists(file1), f"Le fichier source n'existe pas: {file1}"
    assert os.path.exists(file2), f"Le fichier reçu n'existe pas: {file2}"
    assert filecmp.cmp(file1, file2, shallow=False), f"{file1} et {file2} ne sont pas identiques"


# ====================== TESTS =========================

def test_casual():
    server = run_server()
    try:
        run_client(os.path.join(DOWNLOADS, "normal.txt"), f"http://localhost:{PORT}/test.txt")
    finally:
        kill_proc(server, "SERVER")

    assert_files_equal(
        os.path.join(ROOT, "test.txt"),
        os.path.join(DOWNLOADS, "normal.txt")
    )


def test_empty_payload():
    server = run_server()
    try:
        run_client(os.path.join(DOWNLOADS, "empty_out.txt"), f"http://localhost:{PORT}/empty.txt")
    finally:
        kill_proc(server, "SERVER")

    assert_files_equal(
        os.path.join(ROOT, "empty.txt"),
        os.path.join(DOWNLOADS, "empty_out.txt")
    )


def test_delay():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "0", "-e", "0", "-c", "0", "-d", "500", "-R"])
    try:
        run_client(os.path.join(DOWNLOADS, "delai.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim, "LINKSIM")
        kill_proc(server, "SERVER")

    assert_files_equal(
        os.path.join(ROOT, "test.txt"),
        os.path.join(DOWNLOADS, "delai.txt")
    )


def test_delay_packet_loss():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "30", "-e", "0", "-c", "0", "-d", "500", "-R"])
    try:
        run_client(os.path.join(DOWNLOADS, "delai_pl.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim, "LINKSIM")
        kill_proc(server, "SERVER")

    assert_files_equal(
        os.path.join(ROOT, "test.txt"),
        os.path.join(DOWNLOADS, "delai_pl.txt")
    )


def test_delay_packet_loss_error_trunc():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "30", "-e", "20", "-c", "20", "-d", "500", "-R"])
    try:
        run_client(os.path.join(DOWNLOADS, "delai_pl_et_1.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim, "LINKSIM")
        kill_proc(server, "SERVER")

    assert_files_equal(
        os.path.join(ROOT, "test.txt"),
        os.path.join(DOWNLOADS, "delai_pl_et_1.txt")
    )


def test_delay_packet_loss_error_trunc_jitter():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "30", "-e", "20", "-c", "20", "-d", "500", "-j", "5", "-R"])
    try:
        run_client(os.path.join(DOWNLOADS, "delai_pl_et_2.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim, "LINKSIM")
        kill_proc(server, "SERVER")

    assert_files_equal(
        os.path.join(ROOT, "test.txt"),
        os.path.join(DOWNLOADS, "delai_pl_et_2.txt")
    )