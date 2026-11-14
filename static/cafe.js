/*
  cafe.js - Café daily-orders page (Issue #6)

  What this file does:
  1. After a lunch is updated, moves keyboard focus to that lunch's message,
     so the attendant (and screen readers) know it worked.
  2. Before marking a lunch unavailable, checks a reason was typed, and shows
     the same message the server would. app.py checks again.
  3. Reloads the page if the browser's Back button shows an old copy.
*/

// Wait for "load": the browser jumps to the updated lunch's card (the #lunch-…
// part of the address) while loading, and that jump would undo an earlier focus.
window.addEventListener("load", function () {
  const message = document.querySelector(".lunch-card-message");
  if (message) {
    message.scrollIntoView({ block: "center" });
    message.focus({ preventScroll: true });
  }
});

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".unavailable-form form").forEach(function (form) {
    const reason = form.querySelector("textarea");
    const error = form.querySelector(".field-error");

    form.addEventListener("submit", function (event) {
      if (reason.value.trim() === "") {
        event.preventDefault();
        error.textContent = "Please explain why this lunch is unavailable. The parent will see this note.";
        error.hidden = false;
        reason.setAttribute("aria-invalid", "true");
        reason.closest(".field").classList.add("field-invalid");
        reason.focus();
      }
    });
  });
});

window.addEventListener("pageshow", function (event) {
  if (event.persisted) {
    window.location.reload();
  }
});
