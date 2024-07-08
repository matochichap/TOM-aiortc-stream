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
    try:
        names = extract_device_names(list_video_devices())
    except FileNotFoundError:
        print("ffmpeg not found. Please install ffmpeg.")
        return devices
    for name, media in names:
        devices[media].append(name)
    return devices


if __name__ == "__main__":
    print(get_devices())
