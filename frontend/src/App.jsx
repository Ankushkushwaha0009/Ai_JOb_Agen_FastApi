import { useEffect, useState } from "react";

const App = () => {
  const [message, setMessage] = useState("Connecting to backend....");
  const [error, setError] = useState("");
  const [file, setFile] = useState(null);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch("http://127.0.0.1:8000/");
        if (!response.ok) {
          throw new Error("Backend request failed ...");
        }
        const data = await response.json();
        setMessage(data.message);
      } catch (error) {
        setError("Could not connect to the backend....");
      }
    };
    fetchData();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setUploadMessage("");
    setUploadError("");
    if (!file) {
      setUploadError("Please select a PDF resume");
    }
    const formData = new FormData();
    formData.append("file", file);
    try {
      setUploading(true);
      const response = await fetch("http://127.0.0.1:8000/resume/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      console.log(data);
      if (!response.ok) {
        throw new Error(data.detail || "Upload failed");
      }
      setUploadMessage(`Upload successfully : ${data.filename}`);
    } catch (err) {
      setUploadError(err.message || "Could not upload resume");
    } finally {
      setUploading(false);
    }
  };

  return (
    <main>
      <h1> Ai Job Agent ...</h1>
      <p> {message} </p>
      {error && <p> {error} </p>}
      <hr />
      <h2> Upload your resume </h2>
      <form onSubmit={handleSubmit}>
        <input
          type="file"
          accept=".pdf , application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <button type="submit" disabled={uploading}>
          {uploading ? "Uploading...." : "Upload Resume"}
        </button>
      </form>

      {uploadMessage && <p> {uploadMessage} </p>}
      {uploadError && <p> {uploadError} </p>}
    </main>
  );
};

export default App;
