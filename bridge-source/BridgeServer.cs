using System;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Collections.Concurrent;
using Autodesk.Revit.UI;

namespace RevitAgentBridge
{
    /// <summary>
    /// Static registry holding references to the active BridgeServer and ExternalEvent.
    /// Set by the pyRevit extension script on startup; read by the C# HTTP listener
    /// to dispatch requests into Revit's main thread.
    /// </summary>
    public static class BridgeRegistry
    {
        /// <summary>The running HTTP server instance, or null if not started.</summary>
        public static BridgeServer ActiveServer { get; set; }

        /// <summary>The ExternalEvent used to marshal work onto Revit's main thread.</summary>
        public static ExternalEvent ActiveEvent { get; set; }
    }

    /// <summary>
    /// Represents a single tool execution request queued from the HTTP listener
    /// to be processed on Revit's main thread via the ExternalEvent mechanism.
    /// </summary>
    public class AgentTask : IDisposable
    {
        /// <summary>
        /// The raw JSON payload from the HTTP request body.
        /// Contains the tool name and input arguments.
        /// </summary>
        public string RequestJson { get; }

        /// <summary>
        /// The JSON result string written by the Python executor after processing.
        /// Defaults to "{}" until the task completes.
        /// </summary>
        public string ResultJson { get; set; }

        /// <summary>
        /// Signalled when the task has completed (success, error, or timeout).
        /// The HTTP listener thread waits on this event before sending the response.
        /// </summary>
        public AutoResetEvent CompletionEvent { get; }

        /// <summary>
        /// Creates a new agent task with the given JSON request payload.
        /// </summary>
        /// <param name="json">Raw JSON string from the HTTP POST body.</param>
        public AgentTask(string json)
        {
            RequestJson = json ?? "{}";
            ResultJson = "{}";
            CompletionEvent = new AutoResetEvent(false);
        }

        /// <summary>
        /// Releases the underlying WaitHandle (AutoResetEvent) resources.
        /// </summary>
        public void Dispose()
        {
            CompletionEvent?.Close();
        }
    }

    /// <summary>
    /// Handles ExternalEvent callbacks on Revit's main thread.
    /// Maintains a thread-safe queue of AgentTasks and executes them
    /// sequentially using the registered Python callback.
    /// </summary>
    public class AgentExternalEventHandler : IExternalEventHandler
    {
        /// <summary>Thread-safe FIFO queue of pending tool execution tasks.</summary>
        private readonly ConcurrentQueue<AgentTask> _taskQueue = new ConcurrentQueue<AgentTask>();

        /// <summary>
        /// The native Python callback function registered by the pyRevit extension.
        /// Accepts (UIApplication, request_json_string) and returns a result JSON string.
        /// </summary>
        public Func<UIApplication, string, string> PythonExecutor { get; set; }

        /// <summary>
        /// Add a task to the execution queue. Called from the HTTP listener thread.
        /// </summary>
        /// <param name="task">The AgentTask to execute on Revit's main thread.</param>
        public void EnqueueTask(AgentTask task)
        {
            if (task != null)
            {
                _taskQueue.Enqueue(task);
            }
        }

        /// <summary>
        /// Process all queued tasks on Revit's main thread.
        /// Called by the Revit API when the ExternalEvent is raised.
        /// Each task is dequeued, executed via the Python callback, and signalled complete.
        /// </summary>
        /// <param name="app">The Revit UIApplication providing access to the active document.</param>
        public void Execute(UIApplication app)
        {
            while (_taskQueue.TryDequeue(out AgentTask task))
            {
                try
                {
                    if (PythonExecutor != null)
                    {
                        // Safely execute the Python handler directly on Revit's main thread
                        task.ResultJson = PythonExecutor(app, task.RequestJson);
                    }
                    else
                    {
                        task.ResultJson = "{\"status\":\"error\",\"message\":\"Python execution delegate is not registered inside Revit AppDomain.\"}";
                    }
                }
                catch (Exception ex)
                {
                    task.ResultJson = $"{{\"status\":\"error\",\"message\":\"C# Bridge execution crash: {ex.Message}\"}}";
                }
                finally
                {
                    task.CompletionEvent.Set();
                }
            }
        }

        /// <summary>
        /// Returns the handler name shown in Revit's External Event log.
        /// </summary>
        /// <returns>Human-readable handler name.</returns>
        public string GetName()
        {
            return "BIM Agent External Event Handler";
        }
    }

    /// <summary>
    /// Lightweight HTTP server running inside the Revit process.
    /// Listens on localhost for tool discovery (GET /tools/) and execution
    /// (POST /execute/) requests from the Python backend, marshalling them
    /// to Revit's main thread via the ExternalEvent mechanism.
    /// </summary>
    public class BridgeServer
    {
        /// <summary>The underlying .NET HTTP listener bound to localhost.</summary>
        private HttpListener _listener;

        /// <summary>Background thread running the blocking accept loop.</summary>
        private Thread _listenerThread;

        /// <summary>The external event handler that processes tool requests on Revit's main thread.</summary>
        private readonly AgentExternalEventHandler _handler;

        /// <summary>The Revit ExternalEvent used to raise work on the main thread.</summary>
        private readonly ExternalEvent _externalEvent;

        /// <summary>Flag controlling the listener thread's run loop.</summary>
        private bool _isRunning;

        /// <summary>
        /// Creates a new BridgeServer with the given handler and external event.
        /// </summary>
        /// <param name="handler">The event handler that processes tool requests.</param>
        /// <param name="externalEvent">The ExternalEvent for marshalling to Revit's main thread.</param>
        /// <exception cref="ArgumentNullException">If handler or externalEvent is null.</exception>
        public BridgeServer(AgentExternalEventHandler handler, ExternalEvent externalEvent)
        {
            _handler = handler ?? throw new ArgumentNullException(nameof(handler));
            _externalEvent = externalEvent ?? throw new ArgumentNullException(nameof(externalEvent));
        }

        /// <summary>
        /// Start the HTTP listener on the specified port.
        /// Binds to http://127.0.0.1:{port}/execute/ and /tools/ endpoints.
        /// Spawns a background thread for the blocking accept loop.
        /// No-op if the server is already running.
        /// </summary>
        /// <param name="port">TCP port to listen on (default: 8080).</param>
        public void Start(int port)
        {
            if (_isRunning) return;

            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/execute/");
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/tools/");
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/health/");
            _listener.Start();
            _isRunning = true;

            _listenerThread = new Thread(ListenLoop)
            {
                IsBackground = true,
                Name = "RevitAgentBridge_HTTP_Listener"
            };
            _listenerThread.Start();
        }

        /// <summary>
        /// Write a JSON string as the HTTP response body.
        /// Sets Content-Type to application/json and Content-Length.
        /// </summary>
        /// <param name="context">The HTTP listener context to respond to.</param>
        /// <param name="json">The JSON string to write as the response body.</param>
        private void WriteJsonResponse(HttpListenerContext context, string json)
        {
            try
            {
                byte[] buffer = Encoding.UTF8.GetBytes(json);
                context.Response.ContentType = "application/json";
                context.Response.ContentLength64 = buffer.Length;
                context.Response.OutputStream.Write(buffer, 0, buffer.Length);
            }
            finally
            {
                try
                {
                    context.Response.Close();
                }
                catch { }
            }
        }

        /// <summary>
        /// Main accept loop running on a background thread.
        /// Blocks on GetContext() and routes requests:
        /// - GET  /tools/   — discover available tool schemas
        /// - POST /execute/ — execute a named tool with arguments
        /// Both paths enqueue an AgentTask and raise the ExternalEvent.
        /// Requests time out after 120 seconds.
        /// </summary>
        private void ListenLoop()
        {
            while (_isRunning && _listener != null && _listener.IsListening)
            {
                HttpListenerContext context = null;
                try
                {
                    context = _listener.GetContext();
                    HttpListenerRequest request = context.Request;
                    string path = request.Url.AbsolutePath.TrimEnd('/').ToLowerInvariant();

                    if (path == "/health")
                    {
                        WriteJsonResponse(context, "{\"status\":\"success\",\"message\":\"Bridge server is responsive.\"}");
                    }
                    else if (path == "/tools")
                    {
                        // GET /tools/ — inject a get_tools request into the Python router
                        // so the daemon can auto-discover all registered tool schemas.
                        string getToolsPayload = "{\"tool\":\"get_tools\",\"input\":{}}";
                        using (var toolsTask = new AgentTask(getToolsPayload))
                        {
                            _handler.EnqueueTask(toolsTask);
                            _externalEvent.Raise();
                            
                            if (toolsTask.CompletionEvent.WaitOne(120000))
                            {
                                WriteJsonResponse(context, toolsTask.ResultJson);
                            }
                            else
                            {
                                context.Response.StatusCode = 504;
                                WriteJsonResponse(context, "{\"status\":\"error\",\"message\":\"Revit request timed out after 120 seconds.\"}");
                            }
                        }
                    }
                    else if (path == "/execute")
                    {
                        // POST /execute/ — standard tool execution path
                        string jsonPayload;
                        using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                        {
                            jsonPayload = reader.ReadToEnd();
                        }

                        using (var task = new AgentTask(jsonPayload))
                        {
                            _handler.EnqueueTask(task);
                            _externalEvent.Raise();

                            if (task.CompletionEvent.WaitOne(120000))
                            {
                                WriteJsonResponse(context, task.ResultJson);
                            }
                            else
                            {
                                context.Response.StatusCode = 504;
                                WriteJsonResponse(context, "{\"status\":\"error\",\"message\":\"Revit request timed out after 120 seconds.\"}");
                            }
                        }
                    }
                    else
                    {
                        context.Response.StatusCode = 404;
                        WriteJsonResponse(context, "{\"status\":\"error\",\"message\":\"Unknown endpoint.\"}");
                    }
                }
                catch (HttpListenerException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    // Prevent thread crash on unexpected errors and ensure context is closed
                    if (context != null)
                    {
                        try
                        {
                            context.Response.StatusCode = 500;
                            WriteJsonResponse(context, "{\"status\":\"error\",\"message\":\"Bridge internal exception: " + ex.Message + "\"}");
                        }
                        catch
                        {
                            try { context.Response.Close(); } catch { }
                        }
                    }
                }
            }
        }

        /// <summary>
        /// Gracefully stop the HTTP server.
        /// Stops the listener, closes the socket, and joins the listener thread.
        /// Safe to call multiple times.
        /// </summary>
        public void Stop()
        {
            _isRunning = false;
            if (_listener != null)
            {
                try
                {
                    _listener.Stop();
                    _listener.Close();
                }
                catch { }
                _listener = null;
            }

            if (_listenerThread != null && _listenerThread.IsAlive)
            {
                _listenerThread.Join(1000);
                _listenerThread = null;
            }
        }
    }
}