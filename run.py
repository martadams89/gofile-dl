import argparse
import logging
import os
from pathvalidate import sanitize_filename
import requests
import hashlib
import time

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(funcName)20s()][%(levelname)-8s]: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("GoFile")

class GoFileMeta(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

class GoFile(metaclass=GoFileMeta):
    def __init__(self) -> None:
        self.token = ""
        self.wt = ""
    def count_files(self, children: dict) -> int:
        count = 0
        for child in children.values():
            if child["type"] == "folder":
                count += self.count_files(child.get("children", {}))
            else:
                count += 1
        return count
    def update_token(self) -> None:
        if self.token == "":
            data = requests.post("https://api.gofile.io/accounts").json()
            if data.get("status") == "ok":
                self.token = data["data"].get("token", "")
                logger.info(f"Updated token: {self.token}")
            else:
                logger.error("Cannot get token")
    def update_wt(self) -> None:
        if self.wt == "":
            alljs = requests.get("https://gofile.io/dist/js/global.js").text
            if 'appdata.wt = "' in alljs:
                self.wt = alljs.split('appdata.wt = "')[1].split('"')[0]
                logger.info(f"Updated wt: {self.wt}")
            else:
                logger.error("Cannot get wt")
    def execute(self, dir: str, content_id: str = None, url: str = None, password: str = None, 
                progress_callback=None, cancel_event=None, name_callback=None, 
                overall_progress_callback=None, start_time: float = None, 
                file_progress_callback=None, pause_callback=None) -> None:
        if content_id is not None:
            self.update_token()
            self.update_wt()
            hash_password = hashlib.sha256(password.encode()).hexdigest() if password else ""
            response = requests.get(
                f"https://api.gofile.io/contents/{content_id}?wt={self.wt}&cache=true&password={hash_password}",
                headers={"Authorization": "Bearer " + self.token},
            )
            data = response.json()
            if data.get("status") != "ok":
                logger.error("API error: %s", data)
                return
            if data["data"].get("passwordStatus", "passwordOk") != "passwordOk":
                logger.error("Invalid password: %s", data["data"].get("passwordStatus"))
                return
            if data["data"]["type"] == "folder":
                dirname = data["data"]["name"]
                if name_callback:
                    name_callback(sanitize_filename(dirname))
                folder_path = os.path.join(dir, sanitize_filename(dirname))
                os.makedirs(folder_path, exist_ok=True)
                children = data["data"].get("children", {})
                if not children:
                    logger.error("No files/folders found in folder response: %s", data)
                    return
                overall_total = float(self.count_files(children))
                files_completed = 0.0
                for id, child in children.items():
                    if cancel_event and cancel_event.is_set():
                        break
                    try:
                        if child["type"] == "folder":
                            prev = float(self.count_files(child.get("children", {})))
                            self.execute(
                                dir=folder_path, content_id=id, password=password,
                                progress_callback=progress_callback, cancel_event=cancel_event,
                                name_callback=name_callback, overall_progress_callback=overall_progress_callback,
                                start_time=start_time, file_progress_callback=file_progress_callback,
                                pause_callback=pause_callback  # Pass pause_callback to recursive calls
                            )
                            files_completed += prev
                        else:
                            filename = child["name"]
                            file_path = os.path.join(folder_path, sanitize_filename(filename))
                            link = child["link"]
                            if callable(file_progress_callback):
                                file_progress_callback(file_path, 0)  # register start (0%)
                            self.download(
                                link, file_path, progress_callback=progress_callback, 
                                cancel_event=cancel_event, file_progress_callback=file_progress_callback,
                                pause_callback=pause_callback  # Pass pause_callback to download
                            )
                            if callable(file_progress_callback):
                                file_progress_callback(file_path, 100)  # file complete
                            files_completed += 1.0
                    except Exception as e_inner:
                        logger.error(f"Error downloading child {id}: {e_inner}")
                        continue
                    if overall_progress_callback and overall_total > 0:
                        percent = int((files_completed / overall_total) * 100)
                        overall_progress_callback(percent, "N/A")
                if overall_progress_callback:
                    overall_progress_callback(100, "N/A")
            else:
                filename = data["data"]["name"]
                file_path = os.path.join(dir, sanitize_filename(filename))
                link = data["data"]["link"]
                if callable(name_callback):
                    name_callback(sanitize_filename(filename))
                if callable(file_progress_callback):
                    file_progress_callback(file_path, 0)
                self.download(link, file_path, progress_callback=progress_callback, cancel_event=cancel_event, file_progress_callback=file_progress_callback, pause_callback=pause_callback)
                if callable(file_progress_callback):
                    file_progress_callback(file_path, 100)
        elif url is not None:
            if url.startswith("https://gofile.io/d/"):
                cid = url.split("/")[-1]
                self.execute(dir=dir, content_id=cid, password=password,
                             progress_callback=progress_callback, cancel_event=cancel_event,
                             name_callback=name_callback, overall_progress_callback=overall_progress_callback,
                             start_time=start_time, file_progress_callback=file_progress_callback, pause_callback=pause_callback)
            else:
                logger.error(f"Invalid URL: {url}")
        else:
            logger.error("Invalid parameters")
    def download(self, link: str, file: str, chunk_size: int = 8192, progress_callback=None, 
                 cancel_event=None, file_progress_callback=None, pause_callback=None) -> None:
        temp = file + ".part"
        try:
            file_dir = os.path.dirname(file)
            os.makedirs(file_dir, exist_ok=True)
            size = os.path.getsize(temp) if os.path.exists(temp) else 0
            with requests.get(
                link, headers={
                    "Cookie": f"accountToken={self.token}",
                    "Range": f"bytes={size}-"
                }, stream=True
            ) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("Content-Length", 0)) + size
                downloaded = size
                with open(temp, "ab") as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        # Check for pause - if paused, wait until unpaused
                        if pause_callback and pause_callback():
                            while pause_callback():
                                time.sleep(0.5)  # Sleep for half a second before checking again
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            percentage = int(downloaded * 100 / total_size)
                            progress_callback(percentage)
                        if file_progress_callback:
                            file_progress_callback(file, int(downloaded * 100 / total_size))
                        if cancel_event and cancel_event.is_set():
                            logger.info("Download cancelled")
                            raise Exception("Cancelled")
                os.rename(temp, file)
                if file_progress_callback:
                    file_progress_callback(file, 100)
                logger.info(f"Downloaded: {file} ({link})")
                
        except Exception as e:
            logger.error(f"Failed to download ({e}): {file} ({link})")
            if os.path.exists(temp):
                os.remove(temp)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("-d", type=str, dest="dir", help="output directory")
    parser.add_argument("-p", type=str, dest="password", help="password")
    args = parser.parse_args()
    out_dir = args.dir if args.dir is not None else "./output"
    GoFile().execute(dir=out_dir, url=args.url, password=args.password,
                      progress_callback=lambda p: logger.info(f"Overall progress: {p}%"),
                      overall_progress_callback=lambda p, eta: logger.info(f"Overall progress: {p}% | ETA: {eta}"),
                      name_callback=lambda name: logger.info(f"Task name set to: {name}"),
                      file_progress_callback=lambda f, p: logger.info(f"File {f} progress: {p}%"))
if __name__ == "__main__":
    main()