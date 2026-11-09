/*
  script.js - Issue #2: Select a Lunch Package

  What this file does:
  1. Shows which package is selected and how many lunches it includes.
  2. Keeps a live counter, e.g. "3 of 4 lunches selected".
  3. Stops the parent from checking more days than the package allows.
  4. Shows a clear message when the limit is reached.

  app.py checks the limit again on the server, so this file is about giving
  the parent quick, friendly feedback while they click.
*/

// Wait until the HTML has loaded before looking for elements.
document.addEventListener("DOMContentLoaded", function () {
  // Grab the page elements we need once, so we can reuse them.
  const form = document.getElementById("package-form");
  const packageRadios = document.querySelectorAll('input[name="package"]');
  const dayFieldset = document.getElementById("day-options");
  const dayCheckboxes = document.querySelectorAll('input[name="days"]');
  const packageSummary = document.getElementById("package-summary");
  const lunchCounter = document.getElementById("lunch-counter");
  const limitMessage = document.getElementById("limit-message");
  const formMessage = document.getElementById("form-message");

  // Returns the checked package radio button, or null if none is checked.
  function getSelectedPackage() {
    return document.querySelector('input[name="package"]:checked');
  }

  // Counts how many camp-day checkboxes are checked.
  function countSelectedDays() {
    return document.querySelectorAll('input[name="days"]:checked').length;
  }

  // Shows a message in the limit box. "type" is "info" or "warning" for styling.
  function showLimitMessage(text, type) {
    limitMessage.textContent = text;
    limitMessage.className = "limit-message limit-message-" + type;
    limitMessage.hidden = false;
  }

  function hideLimitMessage() {
    limitMessage.textContent = "";
    limitMessage.hidden = true;
  }

  // Shows the result banner above the button, scrolls to it, and moves focus
  // there so screen readers read it. "type" is "error" or "success".
  function showFormMessage(text, type) {
    formMessage.textContent = text;
    formMessage.className = "alert alert-" + type;
    formMessage.hidden = false;
    revealFormMessage();
  }

  function revealFormMessage() {
    formMessage.scrollIntoView({ block: "center" });
    formMessage.focus({ preventScroll: true });
  }

  function hideFormMessage() {
    formMessage.textContent = "";
    formMessage.hidden = true;
  }

  // Checks the whole selection. Returns an error message, or null if it is valid.
  // These messages match the ones in app.py.
  function getValidationError() {
    const selectedPackage = getSelectedPackage();
    const selectedCount = countSelectedDays();

    if (!selectedPackage && selectedCount === 0) {
      return "Please choose a lunch package and at least one camp day.";
    }
    if (!selectedPackage) {
      return "Please choose a lunch package.";
    }
    if (selectedCount === 0) {
      return "Please choose at least one camp day.";
    }

    const limit = Number(selectedPackage.dataset.lunches);
    if (selectedCount > limit) {
      const extra = selectedCount - limit;
      return (
        "The " + selectedPackage.dataset.name + " includes " + limit +
        " lunches, but " + selectedCount + " days are selected. Please unselect " +
        extra + (extra === 1 ? " day." : " days.")
      );
    }
    return null;
  }

  // Turns unchecked day boxes on or off. Checked boxes always stay clickable
  // so the parent can unselect a day and pick a different one.
  function setUncheckedDaysDisabled(isDisabled) {
    dayCheckboxes.forEach(function (checkbox) {
      if (!checkbox.checked) {
        checkbox.disabled = isDisabled;
      }
    });
  }

  // Main function: runs every time the parent changes a package or a day.
  function updatePage() {
    const selectedPackage = getSelectedPackage();

    // No package yet: camp days stay locked until one is chosen.
    if (!selectedPackage) {
      dayFieldset.disabled = true;
      packageSummary.textContent = "No package selected yet.";
      lunchCounter.textContent = "Choose a package to start selecting days.";
      hideLimitMessage();
      return;
    }

    dayFieldset.disabled = false;

    // Read the package details we stored in data-* attributes in index.html.
    const limit = Number(selectedPackage.dataset.lunches);
    const name = selectedPackage.dataset.name;
    const selectedCount = countSelectedDays();

    packageSummary.textContent =
      "Selected: " + name + " — includes " + limit + " lunches.";
    lunchCounter.textContent =
      selectedCount + " of " + limit + " lunches selected";

    if (selectedCount > limit) {
      // This can happen if the parent picks days, then switches to a smaller package.
      const extra = selectedCount - limit;
      showLimitMessage(
        "The " + name + " includes " + limit + " lunches. Please unselect " +
          extra + (extra === 1 ? " day." : " days."),
        "warning"
      );
      setUncheckedDaysDisabled(true);
    } else if (selectedCount === limit) {
      showLimitMessage(
        "You have reached your " + limit + "-lunch limit. " +
          "To choose a different day, unselect one first.",
        "info"
      );
      setUncheckedDaysDisabled(true);
    } else {
      hideLimitMessage();
      setUncheckedDaysDisabled(false);
    }
  }

  // When the selection changes, any old banner (like "confirmed") is out of
  // date, so hide it and refresh the counter and limit message.
  function handleSelectionChange() {
    hideFormMessage();
    updatePage();
  }

  packageRadios.forEach(function (radio) {
    radio.addEventListener("change", handleSelectionChange);
  });
  dayCheckboxes.forEach(function (checkbox) {
    checkbox.addEventListener("change", handleSelectionChange);
  });

  // Last check before the form is sent. If something is wrong, stop the
  // submit and explain why. If it is valid, Flask checks it again.
  form.addEventListener("submit", function (event) {
    const error = getValidationError();
    if (error) {
      event.preventDefault();
      showFormMessage(error, "error");
    }
  });

  // Run once on page load so the page matches any saved selections.
  updatePage();

  // After submitting, the page reloads with Flask's message. Bring it into
  // view so the parent doesn't miss it.
  if (!formMessage.hidden) {
    revealFormMessage();
  }
});
