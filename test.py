import re
import subprocess


def get_devices():
    def list_video_devices():
        result = subprocess.run(
            "ffmpeg -list_devices true -f dshow -i dummy".split(),
            capture_output=True,
            text=True)
        output = result.stderr
        return output

    def extract_device_names(output):
        pattern = r'"([^"]+)"\s+\((video|audio)\)'
        matches = re.findall(pattern, output)
        return matches

    devices = {"video": [], "audio": []}
    for name, media in extract_device_names(list_video_devices()):
        devices[media].append(name)
    return devices


if __name__ == "__main__":
    print(get_devices())
