import subprocess
import time
import os
import filecmp
import pytest
import signal
import random
import string
import shutil

ROOT = "demo_root"
HOST = "::1"
PORT = 8080
SERVER_SCRIPT = "src/server.py"
CLIENT_SCRIPT = "src/client.py"
LINK_SIM = "./tests/Linksimulator-master/link_sim"

def generate_random_file(path, size_bytes):
    """Génère un fichier texte aléatoire de `size_bytes` octets"""
    chars = string.ascii_letters + string.digits + string.punctuation + " \n"
    with open(path, "w") as f:
        remaining = size_bytes
        while remaining > 0:
            chunk_size = min(1024, remaining)
            chunk = ''.join(random.choices(chars, k=chunk_size))
            f.write(chunk)
            remaining -= chunk_size
        
# Crée le dossier de test et les fichiers initiaux
@pytest.fixture(scope="module", autouse=True)
def setup_demo_root():
    """Prépare le répertoire demo_root et un fichier test aléatoire"""
    if os.path.exists(ROOT):
        shutil.rmtree(ROOT)
    os.makedirs(ROOT)

    # fichier test aléatoire de 50 Ko par exemple
    generate_random_file(os.path.join(ROOT, "test.txt"), size_bytes=200*1024)

    # fichier vide
    open(os.path.join(ROOT, "empty.txt"), "w").close()

    yield

    # cleanup après tests
    shutil.rmtree(ROOT)

def run_server(root=ROOT, host=HOST, port=PORT):
    """Démarre le serveur et retourne le PID"""
    proc = subprocess.Popen(
        ["python3", SERVER_SCRIPT, "--root", root, host, str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(1)  # laisse le serveur démarrer
    return proc

def run_client(save_file, url):
    """Lance le client et attend la fin"""
    subprocess.run(
        ["python3", CLIENT_SCRIPT, "--save", save_file, url],
        check=True
    )

def run_linksim(args):
    """Lance LinkSimulator et retourne le PID"""
    proc = subprocess.Popen([LINK_SIM] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)  # laisse LinkSimulator démarrer
    return proc

def kill_proc(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

def assert_files_equal(file1, file2):
    assert filecmp.cmp(file1, file2), f"{file1} et {file2} ne sont pas identiques"

# ====================== TESTS =========================

def test_casual():
    server = run_server()
    try:
        run_client(os.path.join(ROOT, "normal.txt"), f"http://localhost:{PORT}/test.txt")
    finally:
        kill_proc(server)
    
    assert_files_equal(os.path.join(ROOT, "test.txt"), os.path.join(ROOT, "normal.txt"))
"""

def test_empty_payload():
    empty_file = os.path.join(ROOT, "empty.txt")
    with open(empty_file, "w") as f:
        f.write("")

    server = run_server()
    try:
        run_client(os.path.join(ROOT, "empty_out.txt"), f"http://localhost:{PORT}/empty.txt")
    finally:
        kill_proc(server)
    
    assert_files_equal(empty_file, os.path.join(ROOT, "empty_out.txt"))

def test_delay():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "0", "-e", "0", "-c", "0", "-d", "500", "-R"])
    try:
        run_client(os.path.join(ROOT, "delai.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim)
        kill_proc(server)
    
    assert_files_equal(os.path.join(ROOT, "test.txt"), os.path.join(ROOT, "delai.txt"))

def test_delay_packet_loss():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "10", "-e", "0", "-c", "0", "-d", "500", "-R"])
    try:
        run_client(os.path.join(ROOT, "delai_pl.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim)
        kill_proc(server)
    
    assert_files_equal(os.path.join(ROOT, "test.txt"), os.path.join(ROOT, "delai_pl.txt"))

def test_delay_packet_loss_error_trunc():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "10", "-e", "5", "-c", "5", "-d", "500", "-R"])
    try:
        run_client(os.path.join(ROOT, "delai_pl_et.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim)
        kill_proc(server)
    
    assert_files_equal(os.path.join(ROOT, "test.txt"), os.path.join(ROOT, "delai_pl_et.txt"))
    
def test_delay_packet_loss_error_trunc_jitter():
    server = run_server()
    sim = run_linksim(["-p", "9000", "-P", str(PORT), "-l", "10", "-e", "5", "-c", "5", "-d", "500","-j", "5", "-R"])
    try:
        run_client(os.path.join(ROOT, "delai_pl_et.txt"), "http://localhost:9000/test.txt")
    finally:
        kill_proc(sim)
        kill_proc(server)
    
    assert_files_equal(os.path.join(ROOT, "test.txt"), os.path.join(ROOT, "delai_pl_et.txt"))
    
"""