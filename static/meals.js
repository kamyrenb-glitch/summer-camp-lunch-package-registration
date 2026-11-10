/*
  meals.js - Issue #3: Choose Daily Meals

  What this file does:
  1. Keeps a live counter, e.g. "2 of 4 days have a meal chosen".
  2. Before saving, checks that every day has a meal and points out any
     day that is missing one.
  3. Shows the result message near the save button and moves focus to it.
  4. Keeps unsaved meal choices when the parent clicks
     "Edit camper & contact information".

  app.py checks every choice again on the server, so this file is about giving
  the parent quick, friendly feedback while they click.
*/

// Wait until the HTML has loaded before looking for elements.
document.addEventListener("DOMContentLoaded", function () {
  // Grab the page elements we need once, so we can reuse them.
  const form = document.getElementById("meal-form");
  const dayGroups = document.querySelectorAll(".meal-day");
  const mealCounter = document.getElementById("meal-counter");
  const formMessage = document.getElementById("form-message");

  // True if one of the meals in this day's group is checked.
  function hasMeal(dayGroup) {
    return dayGroup.querySelector('input[type="radio"]:checked') !== null;
  }

  // Shows or hides the "Please choose a meal for Day 3." note for one day.
  function setDayError(dayGroup, showError) {
    dayGroup.classList.toggle("meal-day-invalid", showError);
    dayGroup.querySelector(".meal-day-error").hidden = !showError;
  }

  function updateCounter() {
    const chosen = Array.from(dayGroups).filter(hasMeal).length;
    mealCounter.textContent = chosen + " of " + dayGroups.length + " days have a meal chosen";
  }

  // Makes a readable list, matching join_days() in app.py:
  // "Day 1", "Day 1 and Day 2", "Day 1, Day 2, and Day 3"
  function joinDays(days) {
    if (days.length <= 2) {
      return days.join(" and ");
    }
    return days.slice(0, -1).join(", ") + ", and " + days[days.length - 1];
  }

  // Shows the result banner above the buttons, scrolls to it, and moves focus
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

  // When a meal is picked, that day is fixed, and any old banner
  // (like "saved") is out of date.
  dayGroups.forEach(function (dayGroup) {
    dayGroup.addEventListener("change", function () {
      setDayError(dayGroup, false);
      hideFormMessage();
      updateCounter();
    });
  });

  // Last check before saving. If a day has no meal, stop the submit and say
  // which days need one. If it is valid, Flask checks it again.
  form.addEventListener("submit", function (event) {
    // The Back button keeps unfinished choices, so it skips this check.
    if (event.submitter && event.submitter.value === "back") {
      return;
    }

    const missingDays = [];
    dayGroups.forEach(function (dayGroup) {
      const missing = !hasMeal(dayGroup);
      setDayError(dayGroup, missing);
      if (missing) {
        missingDays.push(dayGroup.dataset.day);
      }
    });

    if (missingDays.length > 0) {
      event.preventDefault();
      showFormMessage("Please choose a meal for " + joinDays(missingDays) + ".", "error");
    }
  });

  // "Edit camper & contact information" is a normal link, but first we send
  // the meals chosen so far to the server so they aren't lost. Without
  // JavaScript the link still works; only unsaved choices would be lost.
  const editCamperLink = document.getElementById("edit-camper-link");
  editCamperLink.addEventListener("click", function (event) {
    event.preventDefault();
    const action = document.createElement("input");
    action.type = "hidden";
    action.name = "action";
    action.value = "edit-camper";
    form.appendChild(action);
    // form.submit() skips the "every day needs a meal" check on purpose.
    form.submit();
  });

  // Run once on page load so the counter matches any saved choices.
  updateCounter();

  // After saving, the page reloads with Flask's message. Bring it into
  // view so the parent doesn't miss it.
  if (!formMessage.hidden) {
    revealFormMessage();
  }
});
