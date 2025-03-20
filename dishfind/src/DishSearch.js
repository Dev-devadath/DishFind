import React, { useState } from "react";
import axios from "axios";
import forkIcon from "./assets/fork_icon.png";

const API_BASE_URL = "https://restaurant-foodrecommender.onrender.com";

function DishSearch() {
  const [dishName, setDishName] = useState("");
  const [location, setLocation] = useState("");
  const [radius, setRadius] = useState(10);
  const [useCurrentLocation, setUseCurrentLocation] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingState, setLoadingState] = useState("initial");
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [userLocation, setUserLocation] = useState(null);

  // Validate inputs before submission
  const validateInputs = () => {
    if (!dishName.trim()) {
      setError("Please enter a dish name");
      return false;
    }

    if (!useCurrentLocation && !location.trim()) {
      setError("Please enter a location or use your current location");
      return false;
    }

    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateInputs()) {
      return;
    }

    setIsLoading(true);
    setLoadingState("fetching");
    setError("");
    setResults(null);

    try {
      // Prepare request data with more explicit values and defaults
      const requestData = {
        dish: dishName.trim(),
        location: location.trim() || "Current Location",
        radius: parseInt(radius) || 10, // Ensure radius is a number with fallback
      };

      // Add coordinates if user wants to use their current location
      if (useCurrentLocation) {
        // Ensure we have valid numeric coordinates
        const lat =
          userLocation && userLocation.latitude
            ? parseFloat(userLocation.latitude)
            : 0;
        const lng =
          userLocation && userLocation.longitude
            ? parseFloat(userLocation.longitude)
            : 0;

        requestData.latitude = isNaN(lat) ? 0 : lat;
        requestData.longitude = isNaN(lng) ? 0 : lng;
        requestData.useGeolocation = true;
      } else {
        // Explicitly set coordinates to 0 when not using geolocation
        requestData.latitude = 0;
        requestData.longitude = 0;
        requestData.useGeolocation = false;
      }

      // Ensure radius is always a valid number
      requestData.radius = Number(requestData.radius);
      if (isNaN(requestData.radius) || requestData.radius <= 0) {
        requestData.radius = 10; // Default to 10km if invalid
      }

      console.log("Sending request data:", JSON.stringify(requestData));

      // Initial request to start searching
      const response = await axios.post(
        `${API_BASE_URL}/api/find-restaurants`,
        requestData
      );

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
            setResults(statusResponse.data.result);
            setIsLoading(false);
            setLoadingState("initial");
          } else if (statusResponse.data.state === "FAILED") {
            clearInterval(pollInterval);
            setError(
              statusResponse.data.result.error ||
                "Failed to find restaurants. Please try again."
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
      }, 2000);
    } catch (error) {
      console.error("Error fetching data:", error);
      setError("Failed to find restaurants. Please try again.");
      setIsLoading(false);
      setLoadingState("initial");
    }
  };

  // Get user's current location when checkbox is checked
  React.useEffect(() => {
    if (useCurrentLocation) {
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (position) => {
            setUserLocation({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
            });
          },
          (error) => {
            console.error("Error getting location:", error);
            setError(
              "Unable to get your current location. Please enter a location manually."
            );
            setUseCurrentLocation(false);
          }
        );
      } else {
        setError(
          "Geolocation is not supported by your browser. Please enter a location manually."
        );
        setUseCurrentLocation(false);
      }
    }
  }, [useCurrentLocation]);

  return (
    <div className="dish-search-container">
      <h2 className="section-title">Find Best Restaurants for Dish</h2>
      <p className="section-subtitle">
        Discover the best places to enjoy your favorite dish
      </p>

      <form className="dish-search-form" onSubmit={handleSubmit}>
        <div className="input-group">
          <label htmlFor="dish-name">Dish Name</label>
          <input
            id="dish-name"
            className="dish-input"
            type="text"
            placeholder="e.g., Biryani, Pizza, Sushi..."
            value={dishName}
            onChange={(e) => setDishName(e.target.value)}
            required
          />
        </div>

        <div className="input-group">
          <label htmlFor="location">Location</label>
          <input
            id="location"
            className="location-input"
            type="text"
            placeholder="e.g., New York, Kochi, London..."
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            disabled={useCurrentLocation}
            required={!useCurrentLocation}
          />
          <div className="location-checkbox-container">
            <input
              id="use-current-location"
              className="location-checkbox"
              type="checkbox"
              checked={useCurrentLocation}
              onChange={() => setUseCurrentLocation(!useCurrentLocation)}
            />
            <label htmlFor="use-current-location" className="checkbox-label">
              Use my precise location for better results
            </label>
          </div>
        </div>

        <div className="input-group">
          <label htmlFor="radius">Radius (km)</label>
          <input
            id="radius"
            className="radius-input"
            type="number"
            min="1"
            max="50"
            value={radius}
            onChange={(e) => setRadius(e.target.value)}
          />
        </div>

        <button className="search-button" type="submit" disabled={isLoading}>
          {isLoading ? (
            <>
              <div className="loading-spinner"></div>
              {loadingState === "fetching"
                ? "Searching..."
                : loadingState === "analyzing"
                ? "Analyzing restaurants..."
                : loadingState === "finalizing"
                ? "Finalizing results..."
                : "Processing..."}
            </>
          ) : (
            <>
              <img src={forkIcon} alt="Fork Icon" className="button-icon" />
              Find Best Restaurants
            </>
          )}
        </button>
      </form>

      <p className="search-note">
        Please note: The search process may take 1-5 minutes to complete as we
        analyze restaurant data for the best recommendations.
      </p>

      {error && <div className="error-message">{error}</div>}

      {results && (
        <div className="restaurant-results">
          <h3 className="results-title">Best Restaurants for {results.dish}</h3>

          {results.restaurants && results.restaurants.length > 0 ? (
            <div className="restaurants-list">
              {results.restaurants.map((restaurant, index) => (
                <div key={index} className="restaurant-card">
                  <div className="restaurant-header">
                    <h4 className="restaurant-name">
                      #{index + 1} {restaurant.name}
                    </h4>
                    <div className="restaurant-rating">
                      <span className="rating-value">
                        {restaurant.rating.toFixed(1)}
                      </span>
                      <span className="rating-stars">★</span>
                      <span className="reviews-count">
                        ({restaurant.reviewsCount} reviews)
                      </span>
                    </div>
                  </div>

                  <p className="restaurant-address">{restaurant.address}</p>

                  {restaurant.analysis && (
                    <div className="dish-analysis">
                      <div className="dish-quality">
                        <span className="quality-label">Dish Quality:</span>
                        <span className="quality-value">
                          {restaurant.analysis.dish_quality || "Unknown"}
                        </span>
                      </div>

                      <p className="dish-description">
                        {restaurant.analysis.dish_description ||
                          "No description available."}
                      </p>

                      {restaurant.analysis.key_points &&
                        restaurant.analysis.key_points.length > 0 && (
                          <ul className="key-points">
                            {restaurant.analysis.key_points.map((point, i) => (
                              <li key={i} className="key-point">
                                {point}
                              </li>
                            ))}
                          </ul>
                        )}

                      {restaurant.analysis.recommendation && (
                        <p className="recommendation">
                          {restaurant.analysis.recommendation}
                        </p>
                      )}
                    </div>
                  )}

                  <a
                    href={restaurant.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="view-on-maps"
                  >
                    View on Google Maps
                  </a>
                </div>
              ))}
            </div>
          ) : (
            <p className="no-results">
              No restaurants found for {results.dish} in {results.location}. Try
              a different dish or location.
            </p>
          )}

          <div className="review-prompt">
            <p>How was your meal? Help others decide!</p>
            <a
              href={`https://www.google.com/search?q=review+${encodeURIComponent(
                results.restaurants[0]?.name || "restaurant"
              )}+${encodeURIComponent(results.location)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="review-button"
            >
              <span className="star-icon">★</span> Leave a Google Review for{" "}
              {results.restaurants[0]?.name || "this restaurant"}
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

export default DishSearch;
