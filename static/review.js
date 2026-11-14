/*
  review.js - Issue #4: Review Order and Total

  What this file does:
  1. After "Confirm Order" is pressed once, turns the button off and changes
     its text, so the order isn't sent twice by accident.
  2. Moves focus to an error message if the page shows one.

  app.py also refuses to save the same order twice, so this file is about
  clear feedback while the order is being saved.
*/

// Wait until the HTML has loaded before looking for elements.
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("confirm-form");
  const button = document.getElementById("confirm-order-button");
  const formMessage = document.getElementById("form-message");

  // There is no Confirm button while a day is already ordered, so just
  // bring the message into view.
  if (!button) {
    revealMessage();
    return;
  }

  form.addEventListener("submit", function (event) {
    // A second press while the first is still being sent does nothing.
    if (button.disabled) {
      event.preventDefault();
      return;
    }
    // Turning the button off right away still lets this first submit go through.
    button.disabled = true;
    button.textContent = "Confirming…";
  });

  // If the browser's Back button brings this page back from its memory,
  // turn the button on again. (The server still won't save a second copy.)
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
      button.disabled = false;
      button.textContent = "Confirm Order";
    }
  });

  revealMessage();

  // If the server sent the parent back with a message, bring it into view.
  function revealMessage() {
    if (!formMessage.hidden) {
      formMessage.scrollIntoView({ block: "center" });
      formMessage.focus({ preventScroll: true });
    }
  }
});
