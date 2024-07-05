const form = document.getElementById('textForm');
const start_btn = document.getElementById('start');
    
form.addEventListener('submit', async function(event) {
    event.preventDefault();

    const formData = new FormData(form);
    const inputText = formData.get('inputText');

    await fetch('/send_message', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: inputText }),
    });
});

start_btn.addEventListener('click', async function() {
    await fetch('/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
});