// liff.js
async function initializeLiff(liffId) {
  await liff.init({ liffId });

  if (!liff.isLoggedIn()) {
    liff.login();
  }

  const profile = await liff.getProfile();
  return profile;
}

async function sendDataToGoogleSheet(data, url) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  return res.ok;
}

async function sendLiffMessage(message) {
  if (liff.isApiAvailable("sendMessages")) {
    await liff.sendMessages([{ type: "text", text: message }]);
  }
}