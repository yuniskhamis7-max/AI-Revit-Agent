using System;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Collections.Concurrent;
using Autodesk.Revit.UI;

namespace RevitAgentBridge
{
    public static class BridgeRegistry
    {
        public static BridgeServer ActiveServer { get; set; }
        public static ExternalEvent ActiveEvent { get; set; }
    }

    public class AgentTask
    {
        public string RequestJson { get; }
        public string ResultJson { get; set; }
        public AutoResetEvent CompletionEvent { get; }

        public AgentTask(string json)
        {
            RequestJson = json ?? "{}";
            ResultJson = "{}";
            CompletionEvent = new AutoResetEvent(false);
        }
    }

    public class AgentExternalEventHandler : IExternalEventHandler
    {
        private readonly ConcurrentQueue<AgentTask> _taskQueue = new ConcurrentQueue<AgentTask>();

        // This delegate holds our native Python callback function
        public Func<UIApplication, string, string> PythonExecutor { get; set; }

        public void EnqueueTask(AgentTask task)
        {
            if (task != null)
            {
                _taskQueue.Enqueue(task);
            }
        }

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

        public string GetName()
        {
            return "BIM Agent External Event Handler";
        }
    }

    public class BridgeServer
    {
        private HttpListener _listener;
        private Thread _listenerThread;
        private readonly AgentExternalEventHandler _handler;
        private readonly ExternalEvent _externalEvent;
        private bool _isRunning;

        public BridgeServer(AgentExternalEventHandler handler, ExternalEvent externalEvent)
        {
            _handler = handler ?? throw new ArgumentNullException(nameof(handler));
            _externalEvent = externalEvent ?? throw new ArgumentNullException(nameof(externalEvent));
        }

        public void Start(int port)
        {
            if (_isRunning) return;

            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/execute/");
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/tools/");
            _listener.Start();
            _isRunning = true;

            _listenerThread = new Thread(ListenLoop)
            {
                IsBackground = true,
                Name = "RevitAgentBridge_HTTP_Listener"
            };
            _listenerThread.Start();
        }

        private void WriteJsonResponse(HttpListenerContext context, string json)
        {
            byte[] buffer = Encoding.UTF8.GetBytes(json);
            context.Response.ContentType = "application/json";
            context.Response.ContentLength64 = buffer.Length;
            context.Response.OutputStream.Write(buffer, 0, buffer.Length);
            context.Response.OutputStream.Close();
        }

        private void ListenLoop()
        {
            while (_isRunning && _listener != null && _listener.IsListening)
            {
                try
                {
                    HttpListenerContext context = _listener.GetContext();
                    HttpListenerRequest request = context.Request;
                    string path = request.Url.AbsolutePath.TrimEnd('/').ToLowerInvariant();

                    if (path == "/tools")
                    {
                        // GET /tools/ — inject a get_tools request into the Python router
                        // so the daemon can auto-discover all registered tool schemas.
                        string getToolsPayload = "{\"tool\":\"get_tools\",\"input\":{}}";
                        var toolsTask = new AgentTask(getToolsPayload);
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
                    else if (path == "/execute")
                    {
                        // POST /execute/ — standard tool execution path
                        string jsonPayload;
                        using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                        {
                            jsonPayload = reader.ReadToEnd();
                        }

                        var task = new AgentTask(jsonPayload);
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
                catch (Exception)
                {
                    // Prevent thread crash
                }
            }
        }

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