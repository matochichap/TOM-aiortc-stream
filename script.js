const form = document.getElementById('textForm');
const connectBtn = document.getElementById('connect');
const disconnectBtn = document.getElementById('disconnect');
const callBtn = document.getElementById('call');
const hangupBtn = document.getElementById('hangup');

form.addEventListener('submit', async function(event) {
    event.preventDefault();

    const formData = new FormData(form);
    const message = formData.get('inputText');

    await fetch('/send_message', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: message }),
    });
});

connectBtn.addEventListener('click', async function() {
    await fetch('/connect', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
});

disconnectBtn.addEventListener('click', async function() {
    await fetch('/disconnect', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
});

callBtn.addEventListener('click', async function() {
    await fetch('/call', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
});

hangupBtn.addEventListener('click', async function() {
    await fetch('/hangup', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
});