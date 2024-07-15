const form = document.getElementById('textForm');
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

callBtn.addEventListener('click', async function() {
    callBtn.disabled = true;
    await fetch('/call', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
});

hangupBtn.addEventListener('click', async function() {
    callBtn.disabled = false;
    await fetch('/hangup', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
});