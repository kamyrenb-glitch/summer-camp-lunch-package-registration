/*
  edit-bar.js - "Editing your order" bar (Issue #4)

  What this file does:
  1. Notices whether the package, days, or meals on this page differ from
     what is saved.
  2. If nothing changed, "Return to Review" goes straight to the review page.
  3. If something changed, it opens a warning first, so changes are never
     lost without the parent choosing to discard them.
*/

// Wait until the HTML has loaded before looking for elements.
document.addEventListener("DOMContentLoaded", function () {
  const bar = document.querySelector(".edit-bar");
  if (!bar) {
    return;
  }
  const form = document.getElementById(bar.dataset.trackForm);
  const returnLink = document.getElementById("return-to-review");
  const dialog = document.getElementById("unsaved-dialog");

  // Describes the checked choices on the page, in the same format app.py
  // uses for data-saved-state, e.g. "package=6-day&days=Day 2&days=Day 4".
  function currentState() {
    return Array.from(form.querySelectorAll("input:checked"))
      .map(function (input) {
        return input.name + "=" + input.value;
      })
      .join("&");
  }

  function hasUnsavedChanges() {
    return currentState() !== bar.dataset.savedState;
  }

  function goToReview() {
    window.location.href = returnLink.href;
  }

  returnLink.addEventListener("click", function (event) {
    if (!hasUnsavedChanges()) {
      return; // Nothing to lose: follow the link to the review page.
    }
    event.preventDefault();
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else if (window.confirm(dialog.querySelector("p").textContent + " Discard them?")) {
      // Very old browsers without <dialog> get a simple yes/no question.
      goToReview();
    }
  });

  dialog.querySelector('[data-dialog="keep"]').addEventListener("click", function () {
    dialog.close();
    returnLink.focus();
  });

  dialog.querySelector('[data-dialog="discard"]').addEventListener("click", goToReview);

  // "Save and Return to Review" (meal page only) is a submit button for the
  // meal form. Close the dialog so any "please choose a meal" message from
  // meals.js can be seen; the form then submits as usual.
  const saveButton = dialog.querySelector('[data-dialog="save"]');
  if (saveButton) {
    saveButton.addEventListener("click", function () {
      dialog.close();
    });
  }
});
