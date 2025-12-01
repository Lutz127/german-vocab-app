document.addEventListener("DOMContentLoaded", () => {

    const cards = document.querySelectorAll(".category-card");
    const quizContainer = document.getElementById("quiz-container");
    const home = document.querySelector(".home-content");


    fetch("/api/settings")
    .then(res => res.json())
    .then(s => {
        if (s.default_mode) quizMode = s.default_mode;
        updateModeButtons();
    });

    // Load user progress from backend
    fetch("/api/progress")
        .then(res => res.json())
        .then(data => {
            userProgress = data;
            // Clear outdated local data if backend returns no progress
            if (Object.keys(data).length === 0) {
                localStorage.removeItem("userProgress");
            }
            localStorage.setItem("userProgress", JSON.stringify(userProgress));
            updateCategoryProgressBars();
        });

    // Disable/enable Failed Words card based on count
    fetch("/api/failed_words_count")
        .then(res => res.json())
        .then(data => {
            const card = document.getElementById("failed-words-card");
            if (!card) return;

            if (data.count === 0) {
                card.dataset.disabled = "true";
                card.classList.add("opacity-40", "cursor-not-allowed");
                card.classList.remove("hover:scale-[1.05]", "hover:shadow-xl");
            } else {
                card.dataset.disabled = "false";
                card.classList.remove("opacity-40", "cursor-not-allowed");
                card.classList.add("hover:scale-[1.05]", "hover:shadow-xl");
            }
        });

    // CATEGORY CLICK HANDLER
    cards.forEach(card => {
        card.addEventListener("click", async () => {

            // Disabled Failed Words card
            if (card.dataset.disabled === "true") return;

            const category = card.dataset.category;

            // Special case: Failed Words mode
            if (category === "failed_words") {
                const response = await fetch("/api/failed_words");
                const failed = await response.json();

                const words = failed.map(item => ({
                    german: item.german || "(unknown)",
                    english: item.english || "(missing)",
                    gender: item.gender || null
                }));

                shuffle(words);
                home.classList.add("hidden");
                startQuiz(words, "failed_words");
                return;
            }

            // NORMAL CATEGORY (A1, A2, ...)
            const level = card.dataset.level;

            const response = await fetch(`/static/data/${level}/${category}.json`);
            if (!response.ok) {
                console.error("JSON file missing:", level, category);
                return;
            }

            const words = await response.json();

            shuffle(words);
            home.classList.add("hidden");

            startQuiz(words, category);
        });
    });

    // Mode button listeners
    const deButton = document.getElementById("mode-de-en");
    const enButton = document.getElementById("mode-en-de");

    if (deButton && enButton) {
        deButton.addEventListener("click", () => {
            quizMode = "de-to-en";
            updateModeButtons();
            if (currentRedrawQuestion) currentRedrawQuestion();
        });

        enButton.addEventListener("click", () => {
            quizMode = "en-to-de";
            updateModeButtons();
            if (currentRedrawQuestion) currentRedrawQuestion();
        });
    }
});
// Shuffles JSON file

function shuffle(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
}

let currentRedrawQuestion = null;  // holds the active showQuestion function
let quizMode = "de-to-en";  // default mode

function updateModeButtons() {
    const de = document.getElementById("mode-de-en");
    const en = document.getElementById("mode-en-de");
    if (!de || !en) return;

    if (quizMode === "de-to-en") {
        de.classList.add("bg-yellow-300", "text-black");
        de.classList.remove("bg-black/40", "text-white");

        en.classList.add("bg-black/40", "text-white");
        en.classList.remove("bg-yellow-300", "text-black");

    } else {
        en.classList.add("bg-yellow-300", "text-black");
        en.classList.remove("bg-black/40", "text-white");

        de.classList.add("bg-black/40", "text-white");
        de.classList.remove("bg-yellow-300", "text-black");
    }
}

function normalizeGerman(str) {
    return str
        .toLowerCase()
        .replace(/ä/g, "a")
        .replace(/ö/g, "o")
        .replace(/ü/g, "u")
        .replace(/ß/g, "ss")
        .replace(/\?/g, "")
        .replace(/\(.*?\)/g, "")
        .replace(/\'/g, "");
}

function formatEnglishWithGender(item) {
    // Show the full English definition with parentheses
    let englishFull = item.english.split("/")[0].trim();

    if (item.gender) {
        const g = item.gender.toLowerCase();
        return `${englishFull} (${g})`;
    }
    return englishFull;
}


/* const userProgress = JSON.parse(localStorage.getItem("userProgress")) || {
    animals: 0, basic_phrases: 0, body: 0, city_places: 0, clothing: 0, colors: 0, common_adjectives: 0, common_verbs: 0, communication: 0, condition: 0, conversation_particles: 0,
    countries_languages: 0, daily_activities: 0, daily_routine_nouns: 0, demonstratives: 0, directions: 0, everyday_objects: 0, family: 0, feelings: 0, food_drinks: 0, geography_basics: 0, hobbies_free_time: 0, home_furniture: 0, household_items: 0,
    media_technology: 0, modal_verbs: 0, nature: 0, negation: 0, numbers: 0, people_descriptions: 0, possessive_pronouns: 0, prepositions: 0, pronouns: 0, quantifiers: 0, school_work_verbs: 0, school: 0,
    sizes_measurements: 0, supermarket: 0, taste: 0, temperatures: 0, test: 0, time: 0, time_expressions: 0, toys: 0, transport_verbs: 0, transport: 0, w_questions: 0, weather: 0, work_jobs: 0
}; */

let userProgress = {};

const categoryGroups = {
    basics: [
        "colors",
        "numbers",
        "time",
        "countries_languages",
        "directions",
        "basic_phrases",
        "communication"
    ],
    grammar_basics: [
        "w_questions",
        "prepositions",
        "pronouns",
        "conversation_particles",
        "negation",
        "time_expressions",
        "possesive_pronouns",
        "demonstratives",
        "quantifiers"
    ]
};

function updateCategoryProgressBars() {

    for (const [category, percent] of Object.entries(userProgress)) {

        const outer = document.querySelector(`.progress-${category}`);
        const inner = outer?.querySelector('.progress-inner');
        if (!inner) continue;   // not on this page

        inner.style.width = percent + "%";

        let color = "#ff3b3b";
        if (percent < 20) color = "#ff3b3b";
        else if (percent < 40) color = "#f79046ff";
        else if (percent < 60) color = "#f7bf46ff";
        else if (percent < 80) color = "#daf746ff";
        else if (percent < 99) color = "#63de4aff";
        else if (percent >= 99) color = "#36ff54ff";

        inner.style.backgroundColor = color;

        if (percent >= 99) {
            outer.classList.add("pulse-glow");
        } else {
            outer.classList.remove("pulse-glow");
        }
    }

    for (const [mainCategory, subcats] of Object.entries(categoryGroups)) {

        const outer = document.querySelector(`.progress-${mainCategory}`);
        if (!outer) continue;  // not on this page

        const inner = outer.querySelector(".progress-inner");
        if (!inner) continue;

        // Sum progress values of all subcategories
        let total = 0;
        let count = 0;

        for (const sub of subcats) {
            if (userProgress[sub] !== undefined) {
                total += userProgress[sub];
                count++;
            }
        }

        // If no subcategories found, set to 0
        const avg = count > 0 ? total / count : 0;

        // Fill bar
        inner.style.width = avg + "%";

        // Apply same color logic
        let color = "#ff3b3b";
        if (avg < 20) color = "#ff3b3b";
        else if (avg < 40) color = "#f79046ff";
        else if (avg < 60) color = "#f7bf46ff";
        else if (avg < 80) color = "#daf746ff";
        else if (avg < 99) color = "#63de4aff";
        else if (avg >= 99) color = "#36ff54ff";

        inner.style.backgroundColor = color;

        if (avg >= 99) {
            outer.classList.add("pulse-glow");
        } else {
            outer.classList.remove("pulse-glow");
        }
    }
}

window.addEventListener("load", () => {
    updateCategoryProgressBars();
});


function returnHome() {

    // Only clear the dynamic quiz question area
    const quizContent = document.getElementById("quiz-content");
    if (quizContent) quizContent.innerHTML = "";

    // Reset timer & progress bar
    const timer = document.getElementById("live-timer");
    if (timer) timer.textContent = "Time: 0m 0.0s";

    const progressBar = document.getElementById("progress-bar");
    if (progressBar) progressBar.style.width = "0%";

    // Hide quiz wrapper (NOT deleting HTML)
    const quiz = document.getElementById("quiz-container");
    quiz.classList.add("hidden");

    // Show homepage
    const home = document.querySelector(".home-content");
    home.classList.remove("hidden");

    document.getElementById("live-timer").classList.remove("hidden");
    document.getElementById("progress-container").classList.remove("hidden");
    document.getElementById("mode-de-en").classList.remove("hidden");
    document.getElementById("mode-en-de").classList.remove("hidden");

    // Update progress bars after DOM reflow
    setTimeout(updateCategoryProgressBars, 50);
}

let activeTimers = [];

function clearAllQuizTimers() {
    for (const timer of activeTimers) clearInterval(timer);
    activeTimers = [];
}

const pulseStyle = document.createElement("style");
pulseStyle.textContent = `
@keyframes pulseGlow {
    0% {
        box-shadow:
            0 0 8px rgba(0,255,0,0.25),
            0 0 16px rgba(0,255,0,0.25),
            0 0 24px rgba(0,255,0,0.25);
    }
    50% {
        box-shadow:
            0 0 14px rgba(0,255,0,0.4),
            0 0 28px rgba(0,255,0,0.4),
            0 0 42px rgba(0,255,0,0.4);
    }
    100% {
        box-shadow:
            0 0 8px rgba(0,255,0,0.25),
            0 0 16px rgba(0,255,0,0.25),
            0 0 24px rgba(0,255,0,0.25);
    }
}
.pulse-glow {
    animation: pulseGlow 1.6s ease-in-out infinite;
}
`;
document.head.appendChild(pulseStyle);



// Quiz logic
function startQuiz(words, category) {

    // FULL RESET
    currentRedrawQuestion = null;  // clear previous redraw function
    clearAllQuizTimers();          // stop leftover timers


    const quizContainer = document.getElementById("quiz-container");
    quizContainer.classList.remove("hidden");
    document.getElementById("progress-bar").style.width = "0%";

    let index = 0;
    let score = 0;
    let startTime = Date.now();
    let timerInterval = setInterval(updateTimer, 100);
    activeTimers.push(timerInterval);

    // Reset UI
    document.getElementById("quiz-content").innerHTML = "";
    document.getElementById("progress-bar").style.width = "0%";
    document.getElementById("live-timer").textContent = "Time: 0m 0.0s";

    function showQuestion() {
        const item = words[index];

        const displayGerman = item.german.split("/").map(s => s.trim())[0];

        document.getElementById("quiz-content").innerHTML = `
            <div class="bg-black/60 p-6 rounded-xl shadow text-center mb-4">
                <p class="text-white text-xl mb-2">
                    ${quizMode === "de-to-en" ? "What is the meaning of:" : "Was bedeutet:"}
                </p>

                <p class="text-yellow-300 text-3xl font-bold">
                    ${quizMode === "de-to-en"
                        ? item.german.split("/")[0].trim()
                        : formatEnglishWithGender(item)
                    }
                </p>

                ${quizMode === "de-to-en" && window.userSettings?.show_examples && item.example
                    ? `<p class="text-gray-300 text-sm italic mt-2">"${item.example}"</p>`
                    : ""
                }

            </div>

            <input id="answer-input"
                autocomplete="off"
                autocorrect="off"
                autocapitalize="off"
                spellcheck="false"
                class="w-full p-4 rounded-xl bg-black/60 text-yellow-300 font-bold text-2xl shadow-inner 
                        placeholder:text-yellow-500/40 outline-none focus:ring-2 focus:ring-yellow-300 text-center caret-transparent"
                placeholder="${quizMode === 'de-to-en' ? 'Type the English meaning...' : 'Type the German meaning...'}">

            <p id="feedback" class="text-lg mt-4"></p>
        `;

        document.getElementById("answer-input").focus();

        const answerInput = document.getElementById("answer-input");
        answerInput.disabled = false;

        let lastTypeTime = 0;

        answerInput.addEventListener("input", () => {
            const now = Date.now();

            // Remove this delay entirely or increase it slightly
            if (now - lastTypeTime > 2) {

                // Instead of reusing the same <audio>, CLONE it
                const original = document.getElementById("type-sound");
                const clone = original.cloneNode(true);

                clone.volume = original.volume;   // keep same volume
                if (window.userSettings?.sound) {
                    clone.play();
                }
                lastTypeTime = now;
                setTimeout(() => clone.remove(), 200);
            }
        });

        document.getElementById("answer-input").addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                checkAnswer();
            }
        });

        updateProgressBar();
    }

    currentRedrawQuestion = showQuestion;

    function checkAnswer() {

        const answer = document.getElementById("answer-input");

        if (answer.value.trim() === "") {
            answer.focus();
            return;
        }

        answer.disabled = true;

        let userInput = answer.value.trim().toLowerCase();

        // Choose correct answer depending on mode
        let correctRaw = (
            quizMode === "de-to-en"
                ? words[index].english.toLowerCase()
                : words[index].german.toLowerCase()
        );

        // Normalize correct answers
        userInput = userInput.replace(/^to\s+/, "");
        userInput = userInput.replace(/\?/g, "");
        userInput = userInput.replace(/\(.*?\)/g, "");

        correctRaw = correctRaw.replace(/to\s+/g, "");
        correctRaw = correctRaw.replace(/\?/g, "");
        correctRaw = correctRaw.replace(/\(.*?\)/g, "");

        let correctList = correctRaw.split("/").map(s => s.trim());

        // If plural mode is enabled AND we are in English → German mode
        if (quizMode === "en-to-de" && window.userSettings?.plurals === true) {
            // If the item has a plural field in JSON
            if (words[index].plural) {
                correctList = words[index].plural
                    .toLowerCase()
                    .split("/")
                    .map(s => s.trim());
            }
        }

        let isCorrect;
        const articleStrict = window.userSettings?.strict === true;

        if (quizMode === "en-to-de") {

            let germanForms = correctList; // already split

            if (articleStrict) {
                // strict: full match including article
                const normalizedUser = normalizeGerman(userInput);
                const normalizedCorrect = germanForms.map(c =>
                    normalizeGerman(c)
                );
                isCorrect = normalizedCorrect.includes(normalizedUser);

            } else {
                // non-strict: strip articles + normalize
                const stripArticle = word =>
                    word.replace(/^(der|die|das)\s+/i, "");

                const normalizedUser = normalizeGerman(
                    stripArticle(
                        userInput.replace(/\(.*?\)/g, "")
                    )
                );

                const normalizedCorrect = germanForms.map(c =>
                    normalizeGerman(
                        stripArticle(
                            c.replace(/\(.*?\)/g, "")
                        )
                    )
                );

                isCorrect = normalizedCorrect.includes(normalizedUser);
            }
        } else {
            isCorrect = correctList.includes(userInput);
        }

        // Apply styling + sounds
        if (isCorrect) {
            answer.style.color = "#36ff54ff";
            answer.style.caretColor = "#36ff54ff";
            answer.style.boxShadow = "0 0 0 2px #36ff54ff inset";
            if (window.userSettings?.sound) {
                document.getElementById("correct-sound").play();
            }
            score++;
        } else {
            answer.style.color = "#ff1515ff";
            answer.style.caretColor = "#ff1515ff";
            answer.style.boxShadow = "0 0 0 2px #ff1515ff inset";
            if (window.userSettings?.sound) {
                document.getElementById("wrong-sound").play();
            }
            answer.value = correctList[0];

            // Save failed word to backend
            fetch("/save_failure", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    category: category,
                    word: words[index].german,
                    english: words[index].english,
                    gender: words[index].gender || null
                })
            });
        }

        index++;

        let delay;

        if (window.userSettings && window.userSettings.speedrun === true) {
            delay = 0;  // Instant transition
        } else {
            delay = isCorrect ? 1000 : 3000;
        }

        if (index < words.length) {
            if (delay === 0) {
                showQuestion();
            } else {
                setTimeout(showQuestion, delay);
            }
        } else {
            if (delay === 0) {
                showResults();
            } else {
                setTimeout(showResults, delay);
            }
            clearInterval(timerInterval);
        }
    }


    function updateTimer() {
        let now = Date.now();
        let elapsed = (now - startTime) / 1000; // seconds

        let minutes = Math.floor(elapsed / 60);
        let seconds = (elapsed % 60).toFixed(2); // keep decimals properly

        let timerDisplay = document.getElementById("live-timer");
        if (timerDisplay) {
            timerDisplay.textContent = `Time: ${minutes}m ${seconds}s`;
        }
    }

    function updateProgressBar() {
        const progress = (index / words.length) * 100;
        document.getElementById("progress-bar").style.width = `${progress}%`;
    }

async function showResults() {

    document.getElementById("quiz-back-button")?.classList.add("hidden");

    let endTime = Date.now();
    let totalTime = (endTime - startTime) / 1000; // full decimal precision
    totalTime = Number(totalTime.toFixed(2));     // keep 2 decimals
    let minutes = Math.floor(totalTime / 60);
    let seconds = (totalTime % 60).toFixed(2);

    // Save the score
    await fetch("/save_score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            category: category,
            score: score,
            time: totalTime
        })
    });

    // Refresh progress from backend after saving score
    fetch("/api/progress")
        .then(r => r.json())
        .then(data => {
            userProgress = data;
            localStorage.setItem("userProgress", JSON.stringify(data));
            updateCategoryProgressBars();
        });

    // Save leaderboard entry (wait for completion)
    await fetch("/save_leaderboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            category: category,
            score: score,
            time: totalTime
        })
    });



    document.getElementById("live-timer").classList.add("hidden");
    document.getElementById("progress-container").classList.add("hidden");
    document.getElementById("mode-de-en").classList.add("hidden");
    document.getElementById("mode-en-de").classList.add("hidden");


    let leaderboardHTML = "";

    if (category !== "failed_words") {
        leaderboardHTML = `
            <h3 class="text-white text-2xl font-bold mt-6">Leaderboard</h3>
            <div id="leaderboard" class="bg-black/40 rounded-xl p-4 w-full max-w-md text-white text-center">
                <p class="text-white/60">Loading...</p>
            </div>
        `;
    }

    document.getElementById("quiz-content").innerHTML = `
        <div class="flex flex-col items-center gap-2">
            <h2 class="text-6xl font-bold text-white text-center">Finished!</h2>
            <p class="text-white text-center text-xl">Your score: <b>${score}/${words.length}</b></p>
            <p class="text-white text-center text-lg">Time: <b>${minutes}m ${seconds}s</b></p>

            ${leaderboardHTML}

            <button id="return-home"
                class="mt-6 bg-yellow-400 text-black font-bold px-6 py-3 rounded-xl hover:bg-yellow-500 transition">
                Back to Home
            </button>
        </div>
    `;


    fetch(`/api/leaderboard/${category}`)
    .then(res => res.json())
    .then(rows => {
        const div = document.getElementById("leaderboard");

        if (rows.length === 0) {
            div.innerHTML = "<p class='text-white/60'>No scores yet. Be the first!</p>";
            return;
        }

        div.innerHTML = rows.map((r, i) => `
            <div class="flex justify-between py-1">
                <span class="text-yellow-300">${i + 1}.</span>
                <span>${r.username}</span>
                <span>${r.time.toFixed(2)}s</span>
            </div>
        `).join("");
    });

    document.getElementById("return-home").addEventListener("click", returnHome);
}
document.addEventListener("click", function (e) {
    if (e.target.id === "quiz-back-button") {
        returnHome();
    }
});
    showQuestion();
}