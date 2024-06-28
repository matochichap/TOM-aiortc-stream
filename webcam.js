function start() {
    console.log("hi");
    return fetch('/offer', {
        headers: {
            'Content-Type': 'application/json'
        },
        method: 'POST'
    });
}

document.getElementById('start').addEventListener('click', start);
