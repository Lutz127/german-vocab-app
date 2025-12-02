document.addEventListener("DOMContentLoaded", () => {

    const startBtn = document.getElementById("start-marathon");
    const home = document.querySelector(".home-content");

    if (!startBtn) {
        console.error("marathon.js: #start-marathon not found");
        return;
    }

    startBtn.addEventListener("click", async () => {

        // Fetch all A1 JSON files
        const categories = [
            "colors","numbers","time","countries_languages","directions",
            "basic_phrases","communication",
            "w_questions","prepositions","pronouns","conversation_particles",
            "negation","time_expressions","possesive_pronouns","demonstratives","quantifiers",
            "family","clothing","home_furniture","people_descriptions","school","work_jobs",
            "transport","hobbies_free_time","media_technology",
            "food_drinks","household_items","everyday_objects","toys",
            "weather","animals","nature","geography_basics","city_places",
            "common_verbs","daily_activities","modal_verbs","transport_verbs",
            "common_adjectives","feelings","sizes_measurements"
        ];

        let allWords = [];

        // Load each file
        for (const cat of categories) {
            try {
                const res = await fetch(`/static/data/A1/${cat}.json`);
                if (!res.ok) continue;

                const data = await res.json();
                allWords.push(...data);

            } catch (err) {
                console.error("Error loading category:", cat, err);
            }
        }

        if (allWords.length === 0) {
            alert("Could not load A1 words. Check JSON paths.");
            return;
        }

        console.log("Loaded words:", allWords.length);

        // Shuffle
        shuffle(allWords);

        // Limit to 200
        const selected = allWords.slice(0, 200);

        // Hide intro screen, show quiz
        home.classList.add("hidden");

        // Start quiz using your existing main.js logic
        startQuiz(selected, "a1_marathon");
    });

});

// Use same shuffle as main.js
function shuffle(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
}