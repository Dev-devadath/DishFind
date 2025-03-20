import React, { useState } from "react";
import InputForm from "./InputForm";
import Results from "./Results";
import DishSearch from "./DishSearch";
import logoImage from "./assets/dining-room.png";
import "./App.css";
import { ThemeProvider } from "./ThemeContext";
import ThemeToggle from "./ThemeToggle";

function App() {
  const [results, setResults] = useState(null);
  // Changed default tab from "dish" to "restaurant" so it starts with the "What to Order?" tab
  const [activeTab, setActiveTab] = useState("restaurant");

  const handleResults = (data) => {
    setResults(data);
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    // Clear results when switching tabs
    if (tab === "dish") {
      setResults(null);
    }
  };

  return (
    <ThemeProvider>
      <div className="App">
        <header className="header">
          <ThemeToggle />
          <div className="logo">
            <img src={logoImage} alt="Restaurant Food Recommender Logo" />
          </div>
          <h1>DishFind.xyz</h1>
          <p className="subtitle">
            Find the best dishes to order at any restaurant or discover
            restaurants serving your favorite dishes
          </p>
        </header>

        <div className="tabs-container">
          <div className="tabs">
            <button
              className={`tab ${activeTab === "restaurant" ? "active" : ""}`}
              onClick={() => handleTabChange("restaurant")}
            >
              What to Order?
            </button>
            <button
              className={`tab ${activeTab === "dish" ? "active" : ""}`}
              onClick={() => handleTabChange("dish")}
            >
              Where to Order?
            </button>
          </div>
        </div>

        {activeTab === "restaurant" ? (
          <>
            <InputForm onResults={handleResults} />
            {results && <Results data={results} />}
          </>
        ) : (
          <DishSearch />
        )}

        <div className="footer">
          <p>
            Made with ❤️ by{" "}
            <a
              href="https://devadath.co"
              target="_blank"
              rel="noopener noreferrer"
            >
              Devadath
            </a>
            <br></br>© 2025 All rights reserved.
          </p>
        </div>
      </div>
    </ThemeProvider>
  );
}

export default App;
