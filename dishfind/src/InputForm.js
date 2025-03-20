import React, { useState } from "react";
import axios from "axios";
import forkIcon from "./assets/fork_icon.png";

const API_BASE_URL = "API_URL";

function InputForm({ onResults }) {
  const [url, setUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingState, setLoadingState] = useState("initial");
  const [error, setError] = useState("");

  // Remove restaurantInfo from this component
  // const [restaurantInfo, setRestaurantInfo] = useState(null);

  const getLoadingMessage = () => {
    switch (loadingState) {
      case "fetching":
        return "Getting restaurant's top reviews...";
      case "analyzing":
        return "Analyzing recommended dishes...";
      case "finalizing":
        return "Preparing your personalized recommendations...";
      default:
        return "Processing...";
    }
  };

  const validateUrl = (url) => {
    if (!url.trim()) {
      setError("Please enter a Google Maps URL");
      return false;
    }

    // Clean the URL by removing any whitespace and converting to lowercase
    const cleanUrl = url.trim().toLowerCase();

    // Check for various Google Maps URL patterns
    const isValidGoogleMapsUrl =
      cleanUrl.includes("google.com/maps") ||
      cleanUrl.includes("maps.app.goo.gl") ||
      cleanUrl.includes("goo.gl/maps") ||
      cleanUrl.startsWith("https://maps.app.goo.gl/") ||
      cleanUrl.startsWith("https://goo.gl/maps/") ||
      cleanUrl.startsWith("https://g.co/kgs/");

    if (!isValidGoogleMapsUrl) {
      console.log("Invalid URL:", cleanUrl); // Debug log
      setError("Please enter a valid Google Maps URL");
      return false;
    }

    setError("");
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateUrl(url)) {
      return;
    }

    setIsLoading(true);
    setLoadingState("fetching");
    setError("");

    try {
      console.log("Sending URL to API:", url);

      // Initial request to start scraping
      const response = await axios.post(`${API_BASE_URL}/api/scrape-reviews`, {
        url: url,
      });

      setLoadingState("analyzing");

      // Poll for results
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await axios.get(
            `${API_BASE_URL}/api/status/${response.data.task_id}`
          );

          if (statusResponse.data.state === "ANALYZING") {
            setLoadingState("analyzing");
          } else if (statusResponse.data.state === "FINALIZING") {
            setLoadingState("finalizing");
          } else if (statusResponse.data.state === "COMPLETED") {
            clearInterval(pollInterval);

            // Pass the URL along with the results
            const resultsWithUrl = {
              ...statusResponse.data.result,
              originalUrl: url,
            };

            onResults(resultsWithUrl);
            setIsLoading(false);
            setLoadingState("initial");
          } else if (statusResponse.data.state === "FAILED") {
            clearInterval(pollInterval);
            setError(
              statusResponse.data.result.error ||
                "Failed to process the URL. Please try again."
            );
            setIsLoading(false);
            setLoadingState("initial");
          }
        } catch (error) {
          console.error("Error polling status:", error);
          setError("Failed to get results. Please try again.");
          clearInterval(pollInterval);
          setIsLoading(false);
          setLoadingState("initial");
        }
      }, 1000);
    } catch (error) {
      console.error("Error fetching data:", error);
      setError("Failed to process the URL. Please try again.");
      setIsLoading(false);
      setLoadingState("initial");
    }
  };

  const handleFindRestaurant = () => {
    window.open(
      "https://www.google.com/maps/search/restaurants+near+me",
      "_blank"
    );
  };

  return (
    <div className="input-container">
      <div
        className="input-label"
        onClick={handleFindRestaurant}
        style={{ cursor: "pointer" }}
      >
        Get The Google Maps Link{" "}
        <span className="find-restaurant-link">
          (Find a restaurant near me)
        </span>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="input-wrapper">
          <div className="search-icon">🔍</div>
          <input
            className="url-input"
            type="text"
            placeholder="Paste Google Maps restaurant link here (e.g., maps.google.com/place/...)"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setError("");
            }}
          />
        </div>
        {error && <div className="error-message">{error}</div>}
        <button className="submit-button" type="submit" disabled={isLoading}>
          {isLoading ? (
            <>
              <div className="loading-spinner"></div>
              {getLoadingMessage()}
            </>
          ) : (
            <>
              <img src={forkIcon} alt="Fork Icon" className="button-icon" />
              What to Order?
            </>
          )}
        </button>
      </form>

      {/* Remove the review prompt from here */}
    </div>
  );
}

export default InputForm;
