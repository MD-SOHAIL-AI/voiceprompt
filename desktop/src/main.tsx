import ReactDOM from "react-dom/client";
import App from "./App";
import { Island } from "./components/Island";
import "./styles.css";

const island = new URLSearchParams(location.search).get("surface") === "island";
document.documentElement.classList.toggle("island-document", island);
ReactDOM.createRoot(document.getElementById("root")!).render(
  island ? <Island /> : <App />,
);
