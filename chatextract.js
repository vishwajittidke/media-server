(() => {
    console.log("Locating chat conversation lines...");
    // Captures custom AI message bubble elements, chat lines, or generic chat rows
    const views = Array.from(document.querySelectorAll('.agent-chat-row, .chat-line, [class*="chat-message"], [class*="chat-row"], .conversation-item, p, span'));
    
    // Filters out core system UI buttons or empty blocks
    const chatText = views
        .map(el => el.innerText ? el.innerText.trim() : "")
        .filter(txt => txt.length > 5 && !txt.includes("Ctrl+") && !txt.includes("Settings"))
        .join('\n\n--- MESSAGE BREAK ---\n\n');

    if (chatText.length < 50) {
        return console.error("Could not capture enough text. Please make sure the chat panel is open and visible on your screen!");
    }

    // Generate and trigger download
    const blob = new Blob([chatText], {type: 'text/plain'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'DIRECT_PROJECT_CHATS.txt';
    a.click();
    console.log("SUCCESS! Check your Windows Downloads folder for DIRECT_PROJECT_CHATS.txt");
})();
